package com.carriez.flutter_hbb

import android.Manifest.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
import android.Manifest.permission.SYSTEM_ALERT_WINDOW
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.hjq.permissions.XXPermissions

/**
 * VIZORA: the VIZORA player app asks every couple of minutes ("com.vizora.remote.ENSURE"). When the screen-sharing
 * service is not running (it crashed, or Android closed it), it is started again exactly the way RustDesk's own
 * "start on boot" does. It acts only after the setup was approved on the device (start on boot is on and its
 * permissions are granted), never more than once in 5 minutes, and does nothing while the service runs.
 * It grants nothing by itself: a connection still needs the device's password.
 */
class VizoraEnsureReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action != "com.vizora.remote.ENSURE" || MainService.isReady) return
        val prefs = ctx.getSharedPreferences(KEY_SHARED_PREFERENCES, Context.MODE_PRIVATE)
        if (!prefs.getBoolean(KEY_START_ON_BOOT_OPT, false)) return
        if (!XXPermissions.isGranted(ctx, REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, SYSTEM_ALERT_WINDOW)) return
        val vz = ctx.getSharedPreferences("vizora", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (now - vz.getLong("vz_restart_at", 0) < 5 * 60000) return
        vz.edit().putLong("vz_restart_at", now).apply()
        Log.i("VIZORA", "service not running: starting it again")
        val it = Intent(ctx, MainService::class.java).apply {
            action = ACT_INIT_MEDIA_PROJECTION_AND_SERVICE
            putExtra(EXT_INIT_FROM_BOOT, true)
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(it) else ctx.startService(it)
        } catch (e: Exception) {
            Log.w("VIZORA", "could not start the service: ${e.message}")
        }
    }
}
