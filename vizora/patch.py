#!/usr/bin/env python3
"""
VIZORA Remote: the changes to RustDesk's Android app, applied at build time (the sources in this fork stay untouched).

1. When the VIZORA player app opens VIZORA Remote, it hands over a permanent password (intent extra "vz_password");
   VIZORA Remote sets it once, so the device can be reached right away.
2. After VIZORA Remote reads its own ID, it tells the VIZORA player app (broadcast "com.vizora.player.REMOTE_ID"),
   which reports it to the VIZORA server: the ID appears in the admin panel by itself.
3. Right after that, a guided setup opens Android's permission screens one after another
   (overlay, screen capture, battery, accessibility) and turns on start-on-boot. The person approves each one.

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
          _vizoraSetup();
        }
        if (id.isNotEmpty) await platformFFI.invokeMethod("vz_report_id", id);
      } catch (_) {}
    }
''', after=True)

# --- Flutter side: guided first-time setup. One VIZORA explanation, then Android's own permission
# screens one after another. Every one of them still needs the person at the device to approve it.
patch(DART, '  /// Stop the screen sharing service.\n', r"""  // VIZORA: guided first-time setup, run when the VIZORA player app installs VIZORA Remote
  Future<void> _vizoraSetup() async {
    await Future.delayed(const Duration(seconds: 2));
    final ok = await parent.target?.dialogManager
        .show<bool>((setState, close, context) {
      submit() => close(true);
      return CustomAlertDialog(
        title: const Text('הגדרת שליטה מרחוק - VIZORA',
            textDirection: TextDirection.rtl),
        content: const Text(
            'המכשיר מנוהל על ידי VIZORA. כדי לאפשר תמיכה מרחוק יופיעו עכשיו כמה חלונות אישור של אנדרואיד, אחד אחרי השני. יש לאשר כל אחד:\n\n'
            '1. הצגה מעל אפליקציות אחרות: להדליק ולחזור אחורה\n'
            '2. צילום המסך: לסמן "אל תציג שוב" אם יש, ולבחור "התחל עכשיו"\n'
            '3. חיסכון בסוללה: לאשר\n'
            '4. נגישות: לבחור VIZORA Remote, להדליק ולחזור אחורה',
            textDirection: TextDirection.rtl),
        actions: [
          dialogButton('Cancel', onPressed: close, isOutline: true),
          dialogButton('OK', onPressed: submit),
        ],
        onSubmit: submit,
        onCancel: close,
      );
    });
    if (ok != true) return;
    await checkRequestNotificationPermission();
    await checkFloatingWindowPermission();
    if (!_isStart) await startService(); // Android asks to approve the screen capture
    for (var i = 0; i < 120 && !_mediaOk; i++) {
      await Future.delayed(const Duration(seconds: 1));
    }
    if (!_mediaOk) return;
    // start on boot, so the service comes back after a power cut
    var battery = await AndroidPermissionManager.check(kRequestIgnoreBatteryOptimizations);
    if (!battery) {
      battery = await AndroidPermissionManager.request(kRequestIgnoreBatteryOptimizations);
    }
    if (battery && await AndroidPermissionManager.check(kSystemAlertWindow)) {
      await parent.target?.invokeMethod(AndroidChannel.kSetStartOnBootOpt, true);
    }
    // input control: the accessibility settings, where the person switches VIZORA Remote on
    if (!_inputOk) {
      AndroidPermissionManager.startAction(kActionAccessibilitySettings);
    }
  }

""")

print('VIZORA patch applied')
