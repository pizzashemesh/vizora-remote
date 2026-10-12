#!/usr/bin/env python3
"""
VIZORA Remote: the changes to RustDesk's Android app, applied at build time (the sources in this fork stay untouched).

1. When the VIZORA player app opens VIZORA Remote, it hands over a permanent password (intent extra "vz_password");
   VIZORA Remote sets it once, so the device can be reached right away. This works whether VIZORA Remote was
   closed (onCreate) or already open (onNewIntent).
2. After VIZORA Remote reads its own ID, it tells the VIZORA player app (broadcast "com.vizora.player.REMOTE_ID"),
   which reports it to the VIZORA server: the ID appears in the admin panel by itself.
3. Each handover also starts a guided setup (native Android, step by step: every time VIZORA Remote comes back
   to the front it opens the next permission screen: overlay, screen capture, battery, accessibility) and turns on
   start-on-boot. The person approves each one on the device.

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
    }

    // VIZORA: guided first-time setup, native so nothing in the app can stop it from showing. Every time
    // VIZORA Remote comes back to the front it opens the next of Android's permission screens; the person
    // approves each one there.
    private var vzBusy = false
    private fun vzSetup() {
        val p = getSharedPreferences("vizora", MODE_PRIVATE)
        if (vzBusy || !p.getBoolean("vz_setup", false)) return
        val step = p.getInt("vz_step", 0)
        val next = { s: Int -> p.edit().putInt("vz_step", s).apply() }
        try {
            when (step) {
                0 -> {
                    vzBusy = true
                    android.app.AlertDialog.Builder(this)
                        .setTitle("הגדרת שליטה מרחוק - VIZORA")
                        .setMessage("המכשיר מנוהל על ידי VIZORA. כדי לאפשר תמיכה מרחוק ייפתחו עכשיו כמה חלונות אישור של אנדרואיד, אחד אחרי השני. יש לאשר כל אחד:\n\n" +
                            "1. הצגה מעל אפליקציות אחרות: להדליק ולחזור אחורה\n" +
                            "2. צילום המסך: לסמן \"אל תציג שוב\" אם יש, ולבחור \"התחל עכשיו\"\n" +
                            "3. חיסכון בסוללה: לאשר\n" +
                            "4. נגישות: לבחור VIZORA Remote, להדליק ולחזור אחורה")
                        .setCancelable(false)
                        .setPositiveButton("התחלה") { _, _ -> vzBusy = false; next(1); vzSetup() }
                        .setNegativeButton("לא עכשיו") { _, _ -> vzBusy = false; p.edit().remove("vz_setup").apply() }
                        .show()
                }
                1 -> {
                    next(2)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !android.provider.Settings.canDrawOverlays(this)) {
                        startActivity(Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                    } else vzSetup()
                }
                2 -> {
                    next(3)
                    if (!MainService.isReady) {
                        Intent(activity, MainService::class.java).also { bindService(it, serviceConnection, Context.BIND_AUTO_CREATE) }
                        requestMediaProjection() // Android asks to approve the screen capture; the app starts the service
                    } else vzSetup()
                }
                3 -> {
                    next(4)
                    val pm = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !pm.isIgnoringBatteryOptimizations(packageName)) {
                        startActivity(Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                    } else vzSetup()
                }
                4 -> {
                    next(5)
                    // start on boot, so the service comes back after a power cut
                    getSharedPreferences(KEY_SHARED_PREFERENCES, MODE_PRIVATE).edit().putBoolean(KEY_START_ON_BOOT_OPT, true).apply()
                    if (!InputService.isOpen) {
                        startActivity(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    } else vzSetup()
                }
                else -> p.edit().remove("vz_setup").remove("vz_step").apply()
            }
        } catch (e: Exception) {
            Log.w("VIZORA", "setup step $step: ${e.message}")
            vzBusy = false
            next(step + 1)
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
          await bind.mainSetPermanentPasswordWithResult(password: pw);
        }
        if (id.isNotEmpty) await platformFFI.invokeMethod("vz_report_id", id);
      } catch (_) {}
    }
''', after=True)

print('VIZORA patch applied')
