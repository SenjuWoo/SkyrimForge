// SkyrimForge.Records: the Mutagen records worker of Skyrim Forge. One JSON request on stdin (or a file path as the
// first argument), one JSON result line on stdout. Verbs: version, find, show, override, new, conflicts, overlap,
// index, validate. It never writes into the game folder: override/new write only the target plugin the caller names.
// Exit codes: 0 ok, 1 findings (validate), 2 named failure, 3 unexpected exception.
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Mutagen.Bethesda;
using Mutagen.Bethesda.Plugins;
using Mutagen.Bethesda.Plugins.Aspects;
using Mutagen.Bethesda.Plugins.Binary.Parameters;
using Mutagen.Bethesda.Plugins.Cache;
using Mutagen.Bethesda.Plugins.Records;
using Mutagen.Bethesda.Skyrim;

internal static class Program
{
    private const string Version = "1.0.0";

    private static int Main(string[] args)
    {
        string text = args.Length > 0 && args[0] != "-" ? File.ReadAllText(args[0]) : Console.In.ReadToEnd();
        JsonObject result;
        int code = 0;
        try
        {
            var req = JsonNode.Parse(text)?.AsObject() ?? throw new Failure("request is not a JSON object");
            var verb = Str(req, "verb") ?? throw new Failure("request has no verb");
            result = verb switch
            {
                "version" => new JsonObject { ["ok"] = true, ["worker"] = Version, ["mutagen"] = typeof(SkyrimMod).Assembly.GetName().Version?.ToString() },
                "find" => Find(req),
                "show" => Show(req),
                "override" => Override(req),
                "new" => New(req),
                "conflicts" => Conflicts(req),
                "overlap" => Overlap(req),
                "index" => Index(req),
                "validate" => Validate(req),
                _ => throw new Failure($"unknown verb {verb}")
            };
            if (result["ok"] is JsonValue okv && okv.GetValue<bool>() == false) code = 1;
        }
        catch (Failure f)
        {
            result = new JsonObject { ["ok"] = false, ["error"] = f.Message, ["fix"] = f.Fix };
            code = 2;
        }
        catch (Exception e)
        {
            result = new JsonObject { ["ok"] = false, ["error"] = $"worker exception: {e.GetType().Name}: {e.Message}",
                ["trace"] = e.StackTrace?.Split('\n').Take(6).Aggregate("", (a, b) => a + b.Trim() + " | ") };
            code = 3;
        }
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Console.WriteLine(result.ToJsonString(new JsonSerializerOptions { WriteIndented = false }));
        return code;
    }

    private sealed class Failure(string message, string fix = "") : Exception(message)
    {
        public string Fix { get; } = fix;
    }

    private static string? Str(JsonObject o, string k) => o[k] is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;
    private static int Int(JsonObject o, string k, int d) => o[k] is JsonValue v && v.TryGetValue<int>(out var i) ? i : d;
    private static bool Bool(JsonObject o, string k) => o[k] is JsonValue v && v.TryGetValue<bool>(out var b) && b;

    // Record type registry (signature <-> getter/setter interface), read from Mutagen's generated registrations.
    private static readonly Lazy<List<(string Sig, Type Getter, Type? Setter)>> Types = new(() =>
    {
        var list = new List<(string, Type, Type?)>();
        foreach (var t in typeof(SkyrimMod).Assembly.GetTypes())
        {
            if (!t.Name.EndsWith("_Registration")) continue;
            var trig = t.GetField("TriggeringRecordType", BindingFlags.Public | BindingFlags.Static);
            var getter = t.GetField("GetterType", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as Type;
            var setter = t.GetField("SetterType", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as Type;
            if (trig == null || getter == null || !typeof(IMajorRecordGetter).IsAssignableFrom(getter)) continue;
            var sig = trig.GetValue(null)?.ToString();
            if (string.IsNullOrEmpty(sig) || sig.Length != 4) continue;
            list.Add((sig, getter, setter));
        }
        return list;
    });

    private static Type GetterFor(string sig) =>
        Types.Value.FirstOrDefault(x => x.Sig.Equals(sig, StringComparison.OrdinalIgnoreCase)).Getter
        ?? throw new Failure($"unknown record type {sig}", "use a 4-letter signature such as WEAP, ARMO, MISC, QUST");

    private static string SigOf(IMajorRecordGetter r)
    {
        foreach (var (sig, getter, _) in Types.Value)
            if (getter.IsInstanceOfType(r) && getter.Name == "I" + r.GetType().Name.Replace("BinaryOverlay", "") + "Getter") return sig;
        foreach (var (sig, getter, _) in Types.Value)
            if (getter.IsInstanceOfType(r)) return sig;
        return "????";
    }

    // Load order: absolute paths (a mod manager's virtual Data) or names relative to data_folder.
    private static List<ISkyrimModGetter> LoadMods(JsonObject req, out string dataFolder)
    {
        dataFolder = Str(req, "data_folder") ?? "";
        var names = req["load_order"]?.AsArray().Select(n => n!.GetValue<string>()).ToList() ?? throw new Failure("load_order missing");
        var mods = new List<ISkyrimModGetter>();
        foreach (var n in names)
        {
            var path = Path.IsPathRooted(n) ? n : Path.Combine(dataFolder, n);
            if (!File.Exists(path)) throw new Failure($"plugin not found: {path}");
            mods.Add(SkyrimMod.CreateFromBinaryOverlay(path, SkyrimRelease.SkyrimSE));
        }
        return mods;
    }

    private static JsonObject Brief(IMajorRecordGetter r, string? mod = null)
    {
        var o = new JsonObject { ["formkey"] = r.FormKey.ToString(), ["editor_id"] = r.EditorID, ["type"] = SigOf(r) };
        try
        {
            if (r is ITranslatedNamedGetter tn && tn.Name?.String is string s) o["name"] = s;
            else if (r is INamedGetter nn && nn.Name is string s2) o["name"] = s2;
        }
        catch (Exception) { /* a missing strings file must not stop a search */ }
        if (mod != null) o["plugin"] = mod;
        return o;
    }

    private static FormKey ParseFormKey(string s) =>
        FormKey.TryFactory(s, out var fk) ? fk : throw new Failure($"not a FormKey: {s}", "use <6 hex digits>:<Plugin.esm>, e.g. 012EB7:Skyrim.esm");

    private static JsonObject Find(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var edid = Str(req, "edid");
        var name = Str(req, "name");
        var type = Str(req, "type");
        var exact = Bool(req, "exact");
        var limit = Int(req, "limit", 50);
        var only = Str(req, "plugin");
        Type? t = type != null ? GetterFor(type) : null;
        var cache = mods.ToImmutableLinkCache();
        var hits = new JsonArray();
        var seen = new HashSet<FormKey>();
        int scanned = 0;
        foreach (var mod in mods)
        {
            if (only != null && !mod.ModKey.FileName.String.Equals(only, StringComparison.OrdinalIgnoreCase)) continue;
            var recs = t != null ? mod.EnumerateMajorRecords(t) : mod.EnumerateMajorRecords();
            foreach (var r in recs)
            {
                scanned++;
                if (edid != null)
                {
                    var e = r.EditorID ?? "";
                    if (exact ? !e.Equals(edid, StringComparison.OrdinalIgnoreCase) : e.IndexOf(edid, StringComparison.OrdinalIgnoreCase) < 0) continue;
                }
                if (name != null)
                {
                    string? nm = null;
                    try { nm = (r as ITranslatedNamedGetter)?.Name?.String ?? (r as INamedGetter)?.Name; } catch (Exception) { }
                    if (nm == null || nm.IndexOf(name, StringComparison.OrdinalIgnoreCase) < 0) continue;
                }
                if (!seen.Add(r.FormKey)) continue;
                var o = Brief(r);
                var chain = new JsonArray();
                foreach (var ctx in cache.ResolveAllContexts(r.FormKey, t ?? typeof(IMajorRecordGetter)))
                    chain.Add(ctx.ModKey.FileName.String);
                o["winning"] = chain.Count > 0 ? chain[0]!.GetValue<string>() : mod.ModKey.FileName.String;
                o["override_chain"] = chain;
                hits.Add(o);
                if (hits.Count >= limit) break;
            }
            if (hits.Count >= limit) break;
        }
        return new JsonObject { ["ok"] = true, ["plugins"] = mods.Count, ["scanned"] = scanned, ["count"] = hits.Count, ["results"] = hits };
    }

    private static JsonObject Show(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var fk = ParseFormKey(Str(req, "formkey") ?? throw new Failure("formkey missing"));
        var cache = mods.ToImmutableLinkCache();
        if (!cache.TryResolveContext(fk, typeof(IMajorRecordGetter), out var ctx))
            throw new Failure($"{fk} is not in the load order");
        var r = (IMajorRecordGetter)ctx.Record;
        var o = Brief(r, ctx.ModKey.FileName.String);
        o["ok"] = true;
        o["record_flags"] = r.MajorRecordFlagsRaw;
        o["form_version"] = (r as ISkyrimMajorRecordGetter)?.FormVersion;
        o["links"] = new JsonArray(r.EnumerateFormLinks().Select(l => (JsonNode)l.FormKey.ToString()).Distinct().Take(200).ToArray());
        o["text"] = r.ToString();
        return o;
    }

    private static SkyrimMod OpenOrCreate(string path, JsonObject req)
    {
        if (File.Exists(path)) return SkyrimMod.CreateFromBinary(path, SkyrimRelease.SkyrimSE);
        var mod = new SkyrimMod(ModKey.FromFileName(Path.GetFileName(path)), SkyrimRelease.SkyrimSE);
        if (Bool(req, "light") || path.EndsWith(".esl", StringComparison.OrdinalIgnoreCase)) mod.ModHeader.Flags |= SkyrimModHeader.HeaderFlag.Small;
        if (Bool(req, "master")) mod.ModHeader.Flags |= SkyrimModHeader.HeaderFlag.Master;
        return mod;
    }

    private static void Write(SkyrimMod mod, string path, List<ISkyrimModGetter>? lo)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(path))!;
        Directory.CreateDirectory(dir);
        // Mutagen checks the file name against the ModKey, so the temp copy keeps the real name in its own folder.
        var tmpDir = Path.Combine(dir, ".skyrimforge-write-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(tmpDir);
        try
        {
            var tmp = Path.Combine(tmpDir, Path.GetFileName(path));
            var p = new BinaryWriteParameters { MastersListOrdering = lo != null ? new MastersListOrderingByLoadOrder(lo.Select(m => m.ModKey)) : MastersListOrderingOption.NoCheck };
            mod.WriteToBinary(tmp, p);
            File.Move(tmp, path, true);
        }
        finally
        {
            Directory.Delete(tmpDir, true);
        }
    }

    private static JsonObject Override(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var target = Str(req, "target") ?? throw new Failure("target plugin path missing");
        var fk = ParseFormKey(Str(req, "formkey") ?? throw new Failure("formkey missing"));
        var cache = mods.ToImmutableLinkCache();
        if (!cache.TryResolveContext(fk, typeof(IMajorRecordGetter), out var ctx))
            throw new Failure($"{fk} is not in the load order");
        var mod = OpenOrCreate(target, req);
        if (mod.ModKey == fk.ModKey) throw new Failure("the target plugin owns this record; edit it directly");
        var copy = ((IMajorRecordGetter)ctx.Record).DeepCopy();
        var group = mod.GetTopLevelGroup(copy.GetType().GetInterfaces().First(i => i.Name == "I" + copy.GetType().Name));
        group.AddUntyped(copy);
        Write(mod, target, mods);
        return new JsonObject { ["ok"] = true, ["target"] = target, ["override"] = Brief(copy), ["from"] = ctx.ModKey.FileName.String };
    }

    private static JsonObject New(JsonObject req)
    {
        var target = Str(req, "target") ?? throw new Failure("target plugin path missing");
        var sig = Str(req, "type") ?? throw new Failure("type missing");
        var edid = Str(req, "edid") ?? throw new Failure("edid missing");
        List<ISkyrimModGetter>? lo = req["load_order"] != null ? LoadMods(req, out _) : null;
        var mod = OpenOrCreate(target, req);
        if (mod.EnumerateMajorRecords().Any(r => edid.Equals(r.EditorID, StringComparison.OrdinalIgnoreCase)))
            throw new Failure($"EditorID {edid} already exists in {Path.GetFileName(target)}");
        var getter = GetterFor(sig);
        var setter = Types.Value.First(x => x.Getter == getter).Setter ?? throw new Failure($"{sig} has no setter type");
        var group = mod.GetTopLevelGroup(setter);
        var light = mod.ModHeader.Flags.HasFlag(SkyrimModHeader.HeaderFlag.Small) || target.EndsWith(".esl", StringComparison.OrdinalIgnoreCase);
        var floor = Int(req, "floor", 0x800);
        var next = Math.Max(mod.ModHeader.Stats.NextFormID, (uint)floor);
        var used = mod.EnumerateMajorRecords().Where(r => r.FormKey.ModKey == mod.ModKey).Select(r => r.FormKey.ID).ToHashSet();
        while (used.Contains(next)) next++;
        if (light && next > 0xFFF) throw new Failure("no free light-plugin FormID left (max 0xFFF)", "split the plugin or drop the light flag");
        var fk = new FormKey(mod.ModKey, next);
        var concrete = typeof(SkyrimMod).Assembly.GetType(setter.Namespace + "." + setter.Name.Substring(1))
            ?? throw new Failure($"no concrete class for {setter.Name}");
        var rec = (IMajorRecord)System.Activator.CreateInstance(concrete, fk, SkyrimRelease.SkyrimSE)!;
        rec.EditorID = edid;
        var script = Str(req, "script");
        if (rec is Quest quest)
        {
            if (script != null)
            {
                quest.VirtualMachineAdapter = new QuestAdapter();
                quest.VirtualMachineAdapter.Scripts.Add(new ScriptEntry { Name = script });
            }
            if (Bool(req, "start_enabled")) quest.Flags |= Quest.Flag.StartGameEnabled;
        }
        else if (script != null)
        {
            throw new Failure($"attaching a script on create is supported for QUST here, not {sig}", "override the record and attach it there");
        }
        group.AddUntyped(rec);
        mod.ModHeader.Stats.NextFormID = next + 1;
        Write(mod, target, lo);
        return new JsonObject { ["ok"] = true, ["target"] = target, ["record"] = Brief(rec), ["light"] = light, ["object_id"] = $"{next:X6}" };
    }

    private static JsonObject Conflicts(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var plugin = Str(req, "plugin") ?? throw new Failure("plugin missing");
        var limit = Int(req, "limit", 200);
        var idx = mods.FindIndex(m => m.ModKey.FileName.String.Equals(plugin, StringComparison.OrdinalIgnoreCase));
        if (idx < 0) throw new Failure($"{plugin} is not in the load order");
        var mine = mods[idx].EnumerateMajorRecords().Select(r => r.FormKey).ToHashSet();
        var hits = new JsonArray();
        int total = 0;
        foreach (var m in mods.Skip(idx + 1))
            foreach (var r in m.EnumerateMajorRecords())
                if (mine.Contains(r.FormKey))
                {
                    total++;
                    if (hits.Count < limit) hits.Add(Brief(r, m.ModKey.FileName.String));
                }
        return new JsonObject { ["ok"] = true, ["plugin"] = plugin, ["records"] = mine.Count, ["overridden_later"] = total, ["results"] = hits };
    }

    // EditorID index of the whole load order as JSON lines (winning override per FormKey).
    private static JsonObject Index(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var outPath = Str(req, "out") ?? throw new Failure("out path missing");
        var win = new Dictionary<FormKey, (string Edid, string Sig, string Mod)>();
        long scanned = 0;
        foreach (var mod in mods)
        {
            var name = mod.ModKey.FileName.String;
            foreach (var r in mod.EnumerateMajorRecords())
            {
                scanned++;
                string? e;
                try { e = r.EditorID; } catch (Exception) { e = null; }
                if (string.IsNullOrEmpty(e)) continue;
                win[r.FormKey] = (e, SigOf(r), name);
            }
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath))!);
        using (var w = new StreamWriter(outPath, false, new System.Text.UTF8Encoding(false)))
        {
            foreach (var (fk, v) in win)
                w.WriteLine(new JsonObject { ["edid"] = v.Edid, ["formkey"] = fk.ToString(), ["type"] = v.Sig, ["winning"] = v.Mod }.ToJsonString());
        }
        return new JsonObject { ["ok"] = true, ["plugins"] = mods.Count, ["scanned"] = scanned, ["records"] = win.Count, ["out"] = outPath };
    }

    // For a plugin outside the load order (a build output): which installed plugins also override what it overrides.
    private static JsonObject Overlap(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var target = Str(req, "target") ?? throw new Failure("target plugin path missing");
        if (!File.Exists(target)) throw new Failure($"plugin not found: {target}", "build it first");
        var mine = SkyrimMod.CreateFromBinaryOverlay(target, SkyrimRelease.SkyrimSE);
        var all = mods.Where(m => m.ModKey != mine.ModKey).ToList();
        var cache = all.ToImmutableLinkCache();
        var limit = Int(req, "limit", 200);
        var hits = new JsonArray();
        int overrides = 0, contested = 0;
        foreach (var r in mine.EnumerateMajorRecords())
        {
            if (r.FormKey.ModKey == mine.ModKey) continue;
            overrides++;
            var chain = cache.ResolveAllContexts(r.FormKey, typeof(IMajorRecordGetter)).Select(c => c.ModKey.FileName.String).ToList();
            var others = chain.Where(n => !n.Equals(r.FormKey.ModKey.FileName.String, StringComparison.OrdinalIgnoreCase)).ToList();
            if (others.Count == 0) continue;
            contested++;
            if (hits.Count < limit)
            {
                var o = Brief(r);
                o["also_overridden_by"] = new JsonArray(others.Select(x => (JsonNode)x).ToArray());
                o["winning_without_you"] = chain.FirstOrDefault();
                hits.Add(o);
            }
        }
        return new JsonObject { ["ok"] = true, ["target"] = target, ["overrides"] = overrides, ["contested"] = contested, ["results"] = hits };
    }

    private static JsonObject Validate(JsonObject req)
    {
        var mods = LoadMods(req, out _);
        var target = Str(req, "target") ?? throw new Failure("target plugin path missing");
        if (!File.Exists(target)) throw new Failure($"plugin not found: {target}", "build or create it first");
        var mod = SkyrimMod.CreateFromBinaryOverlay(target, SkyrimRelease.SkyrimSE);
        var errors = new JsonArray();
        var known = mods.Select(m => m.ModKey).ToHashSet();
        foreach (var m in mod.ModHeader.MasterReferences)
            if (!known.Contains(m.Master)) errors.Add(new JsonObject { ["code"] = "MISSING-MASTER", ["message"] = $"master {m.Master} is not in the load order" });
        var cache = mods.Where(m => m.ModKey != mod.ModKey).Append(mod).ToList().ToImmutableLinkCache();
        var light = mod.ModHeader.Flags.HasFlag(SkyrimModHeader.HeaderFlag.Small) || target.EndsWith(".esl", StringComparison.OrdinalIgnoreCase);
        var floor = Int(req, "floor", 0x800);
        int records = 0, dangling = 0;
        foreach (var r in mod.EnumerateMajorRecords())
        {
            records++;
            if (r.FormKey.ModKey == mod.ModKey && light && (r.FormKey.ID < floor || r.FormKey.ID > 0xFFF))
                errors.Add(new JsonObject { ["code"] = "LIGHT-RANGE", ["message"] = $"{r.FormKey} ({r.EditorID}) is outside {floor:X3}-FFF" });
            foreach (var l in r.EnumerateFormLinks())
            {
                if (l.IsNull) continue;
                if (!cache.TryResolveIdentifier(l.FormKey, out _))
                {
                    dangling++;
                    if (dangling <= 50) errors.Add(new JsonObject { ["code"] = "DANGLING-LINK", ["message"] = $"{r.FormKey} ({r.EditorID}) links to missing {l.FormKey}" });
                }
            }
        }
        return new JsonObject { ["ok"] = errors.Count == 0, ["target"] = target, ["records"] = records, ["light"] = light, ["dangling_links"] = dangling, ["errors"] = errors };
    }
}
