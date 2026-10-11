#!/usr/bin/env python3
"""
VIZORA Remote: the changes to RustDesk's Android app, applied at build time (the sources in this fork stay untouched).

1. When the VIZORA player app opens VIZORA Remote, it hands over a permanent password (intent extra "vz_password");
   VIZORA Remote sets it once, so the device can be reached right away.
2. After VIZORA Remote reads its own ID, it tells the VIZORA player app (broadcast "com.vizora.player.REMOTE_ID"),
   which reports it to the VIZORA server: the ID appears in the admin panel by itself.

Every change is checked: if RustDesk's code changed and an anchor is missing, the build stops instead of
producing an app without these features.
"""
import sys

KT = 'flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainActivity.kt'
DART = 'flutter/lib/models/server_model.dart'


def patch(path, anchor, insert, after=False):
    s = open(path, encoding='utf-8').read()
    if 'VIZORA' in s and insert.strip().splitlines()[0].strip() in s:
        return  # already applied
    if s.count(anchor) != 1:
        sys.exit(f'VIZORA patch: anchor not found exactly once in {path}: {anchor!r}')
    s = s.replace(anchor, anchor + insert if after else insert + anchor, 1)
    open(path, 'w', encoding='utf-8').write(s)


# --- Android side: keep the password handed over by the VIZORA app, and pass the ID back to it
patch(KT, '        flutterMethodChannel = MethodChannel(\n', '''        // VIZORA: a permanent password handed over by the VIZORA player app, kept until the app takes it
        intent?.getStringExtra("vz_password")?.let {
            if (it.isNotEmpty()) getSharedPreferences("vizora", MODE_PRIVATE).edit().putString("vz_password", it).apply()
        }
''')
patch(KT, '                "try_sync_clipboard" -> {\n', '''                "vz_take_password" -> {
                    // VIZORA: hand the password to the app once, then forget it
                    val p = getSharedPreferences("vizora", MODE_PRIVATE)
                    val pw = p.getString("vz_password", "") ?: ""
                    p.edit().remove("vz_password").apply()
                    result.success(pw)
                }
                "vz_report_id" -> {
                    // VIZORA: tell the VIZORA player app this device's ID (it reports it to the VIZORA server)
                    try {
                        val i = Intent("com.vizora.player.REMOTE_ID")
                        i.setPackage("com.vizora.player")
                        i.putExtra("id", call.arguments as? String ?: "")
                        sendBroadcast(i)
                    } catch (e: Exception) {
                        Log.w("VIZORA", "could not report the ID: ${e.message}")
                    }
                    result.success(true)
                }
''')

# --- Flutter side: after reading its own ID, set the handed-over password and report the ID
patch(DART, '''  fetchID() async {
    final id = await bind.mainGetMyId();
    if (id != _serverId.id) {
      _serverId.id = id;
      notifyListeners();
    }
''', '''    // VIZORA: the password from the VIZORA player app, and this ID back to it
    if (isAndroid) {
      try {
        final pw = await platformFFI.invokeMethod("vz_take_password");
        if (pw is String && pw.isNotEmpty) {
          await bind.mainSetPermanentPasswordWithResult(password: pw);
        }
        if (id.isNotEmpty) await platformFFI.invokeMethod("vz_report_id", id);
      } catch (_) {}
    }
''', after=True)

print('VIZORA patch applied')
