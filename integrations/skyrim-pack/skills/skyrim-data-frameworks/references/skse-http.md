# SKSE HTTP (Leidtier) — typed dictionaries and local HTTP from Papyrus

Checked: repo README at `8da249b` (2025-01-09); installed DLL `SKSE_HTTP.dll`. Used by AI/NPC bridges (for example
Mantella-style tools). Papyrus interface is modelled on JContainers handles. SE, AE and VR. Statically links libcurl,
cpr and nlohmann/json (no extra DLLs in the game folder).

## Pattern

```papyrus
Function CallServer()
    int request = SKSE_HTTP.createDictionary()                    ; handle
    SKSE_HTTP.setString(request, "requestType", "startConversation")
    SKSE_HTTP.setBool(request, "isInCombatWithPlayer", false)
    SKSE_HTTP.setFloat(request, "testFloat", 0.123)
    int context = SKSE_HTTP.createDictionary()
    SKSE_HTTP.setString(context, "location", "Dragonsreach")
    SKSE_HTTP.setInt(context, "time", 1328)
    SKSE_HTTP.setNestedDictionary(request, "context", context)
    SKSE_HTTP.sendLocalhostHttpRequest(request, 5000, "mantella")  ; http://localhost:5000/mantella
EndFunction

Event OnInit()
    RegisterForModEvent("SKSE_HTTP_OnHttpReplyReceived", "OnHttpReplyReceived")
EndEvent

Event OnHttpReplyReceived(int typedDictionaryHandle)
    string replyType = SKSE_HTTP.getString(typedDictionaryHandle, "replytype", "Error: No reply type received")
    bool likes = SKSE_HTTP.getBool(typedDictionaryHandle, "npcLikesPlayer", false)
    float f = SKSE_HTTP.getFloat(typedDictionaryHandle, "testFloat", 1)
    int ctx = SKSE_HTTP.getNestedDictionary(typedDictionaryHandle, "context", 0)
    int time = SKSE_HTTP.getInt(ctx, "time", 0)
EndEvent
```

## Facts

- Value types: string, int, float, bool, nested dictionary, arrays; dictionaries serialize to and from JSON.
- Getters take a default as the last argument, used when the key is absent.
- The reply arrives as the mod event `SKSE_HTTP_OnHttpReplyReceived` carrying a dictionary handle.
- Requests go to a local server (`sendLocalhostHttpRequest(handle, port, route)`); running that server is the
  user's responsibility.
- The README documents only the calls above. Any other function (arrays, remove/clear, other send variants) must be
  verified from the installed `SKSE_HTTP` script before use; do not guess a name.
