#!/usr/bin/env python3
"""
VIZORA Remote: the changes to RustDesk's Android app, applied at build time (the sources in this fork stay untouched).

1. When the VIZORA player app opens VIZORA Remote, it hands over a permanent password (intent extra "vz_password");
   VIZORA Remote sets it once, so the device can be reached right away. This works whether VIZORA Remote was
   closed (onCreate) or already open (onNewIntent).
2. After VIZORA Remote reads its own ID, it tells the VIZORA player app (broadcast "com.vizora.player.REMOTE_ID"),
   which reports it to the VIZORA server: the ID appears in the admin panel by itself.
3. Each handover also opens VIZORA's setup screen (VizoraSetupActivity.kt): the four approvals (overlay, screen
   capture, battery, accessibility) with a live check mark each, opened one after another; it also turns on
   start-on-boot. The person approves each one on the device, and the progress shows in the VIZORA panel.
4. VizoraEnsureReceiver.kt: the VIZORA player app asks every couple of minutes; when the service isn't running
   (after a crash) it is started again the way RustDesk's start-on-boot does, once the setup was approved.
5. The ID report says whether the handed-over password was really set, so the panel knows it matches.
   It runs from the model every 3 seconds (RustDesk only checks while the "Share screen" tab is open).

Every change is checked: if RustDesk's code changed and an anchor is missing, the build stops instead of
producing an app without these features.
"""
import sys

KT = 'flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainActivity.kt'
DART = 'flutter/lib/models/server_model.dart'


def patch(path, anchor, insert, after=False):
    s = open(path, encoding='utf-8').read()
    if insert.strip().splitlines()[0].strip() in s:
        return  # already applied
    if s.count(anchor) != 1:
        sys.exit(f'VIZORA patch: anchor not found exactly once in {path}: {anchor!r}')
    s = s.replace(anchor, anchor + insert if after else insert + anchor, 1)
    open(path, 'w', encoding='utf-8').write(s)


# --- Android side: keep the password handed over by the VIZORA app (closed or already open)
patch(KT, '        flutterMethodChannel = MethodChannel(\n', '''        // VIZORA: a permanent password handed over by the VIZORA player app (VIZORA Remote was closed)
        vzKeep(intent)
''')
patch(KT, '    override fun onResume() {\n', r'''    // VIZORA: the same handover when VIZORA Remote was already open
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        vzKeep(intent)
    }

    // VIZORA: keep the password until the app takes it, and mark the guided setup as pending
    private fun vzKeep(i: Intent?) {
        val pw = i?.getStringExtra("vz_password") ?: return
        if (pw.isEmpty()) return
        getSharedPreferences("vizora", MODE_PRIVATE).edit()
            .putString("vz_password", pw).putBoolean("vz_setup", true).putInt("vz_step", 0).apply()
        i?.removeExtra("vz_password")
        vzSay("התקבלה סיסמה בפתיחת האפליקציה")
    }

    // VIZORA: progress for the VIZORA panel (through the VIZORA player app)
    private fun vzSay(msg: String) {
        try {
            val b = Intent("com.vizora.player.REMOTE_ID")
            b.setPackage("com.vizora.player")
            b.putExtra("setup", msg)
            sendBroadcast(b)
        } catch (_: Exception) {}
    }

    // VIZORA: after a handover, open VIZORA's own setup screen (VizoraSetupActivity) once
    private fun vzSetup() {
        val p = getSharedPreferences("vizora", MODE_PRIVATE)
        if (!p.getBoolean("vz_setup", false)) return
        p.edit().remove("vz_setup").apply()
        try {
            startActivity(Intent(this, VizoraSetupActivity::class.java))
        } catch (e: Exception) {
            Log.w("VIZORA", "setup screen: ${e.message}")
        }
    }

''')
patch(KT, '        super.onResume()\n', '''        // VIZORA: the next step of the guided setup, once the screen has settled
        window.decorView.postDelayed({ vzSetup() }, 1200)
''', after=True)
patch(KT, '                "try_sync_clipboard" -> {\n', '''                "vz_take_password" -> {
                    // VIZORA: hand the password to the app once, then forget it
                    val p = getSharedPreferences("vizora", MODE_PRIVATE)
                    val pw = p.getString("vz_password", "") ?: ""
                    p.edit().remove("vz_password").apply()
                    result.success(pw)
                }
                "vz_say" -> {
                    vzSay(call.arguments as? String ?: "")
                    result.success(true)
                }
                "vz_report_id" -> {
                    // VIZORA: tell the VIZORA player app this device's ID (it reports it to the VIZORA server)
                    try {
                        val i = Intent("com.vizora.player.REMOTE_ID")
                        i.setPackage("com.vizora.player")
                        val a = call.arguments as? String ?: ""
                        i.putExtra("id", a.substringBefore("|"))
                        if (a.endsWith("|pw")) i.putExtra("pw", true) // the password was just set
                        sendBroadcast(i)
                    } catch (e: Exception) {
                        Log.w("VIZORA", "could not report the ID: ${e.message}")
                    }
                    result.success(true)
                }
''')

# --- Flutter side: after reading its own ID, set the handed-over password, report the ID, run the setup
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
          if (await bind.mainSetPermanentPasswordWithResult(password: pw)) {
            _vzPwSet = true;
            await platformFFI.invokeMethod("vz_say", "הסיסמה הוגדרה במכשיר");
          } else {
            await platformFFI.invokeMethod("vz_say", "הגדרת הסיסמה נכשלה");
          }
        }
        if (id.isNotEmpty) {
          await platformFFI.invokeMethod("vz_report_id", _vzPwSet ? "$id|pw" : id);
          _vzPwSet = false;
        }
      } catch (_) {}
    }
''', after=True)

# the flag above lives on the model, so it survives until the ID is there
patch(DART, '  fetchID() async {\n', '''  bool _vzPwSet = false; // VIZORA: the handed-over password was set, not reported yet

''')

# fetchID (and so the password and the ID report above) runs only while the "Share screen" tab is on screen, and
# VIZORA Remote opens on the "Connection" tab: run it every 3 seconds from the model, whichever tab is open
patch(DART, '''    _serverId = IDTextEditingController(text: _emptyIdShow);
''', '''    // VIZORA: take the handed-over password and report the ID whichever tab is open
    if (isAndroid) {
      Timer.periodic(const Duration(seconds: 3), (_) async {
        try {
          await fetchID();
        } catch (_) {}
      });
    }
''', after=True)

# --- the setup screen: a file of its own, copied next to MainActivity, and declared in the manifest
import os, shutil
for f in ('VizoraSetupActivity.kt', 'VizoraEnsureReceiver.kt'):
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), f), os.path.dirname(KT))
patch('flutter/android/app/src/main/AndroidManifest.xml', '    </application>\n', '''        <!-- VIZORA: the remote-support setup screen -->
        <activity
            android:name="com.carriez.flutter_hbb.VizoraSetupActivity"
            android:exported="false"
            android:theme="@android:style/Theme.DeviceDefault.NoActionBar" />
        <!-- VIZORA: the VIZORA player app asks to bring the service back after a crash -->
        <receiver
            android:name="com.carriez.flutter_hbb.VizoraEnsureReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="com.vizora.remote.ENSURE" />
            </intent-filter>
        </receiver>
''')

print('VIZORA patch applied')
