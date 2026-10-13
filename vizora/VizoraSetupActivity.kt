package com.carriez.flutter_hbb

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * VIZORA: one screen that walks through Android's approvals for remote support (overlay, screen capture,
 * battery, accessibility). Each row shows live whether it is approved and has its own button; "התחלה" opens
 * the missing ones one after another. Android asks the person at the device for every approval, and this
 * screen only opens those requests. Progress is reported to the VIZORA panel through the VIZORA player app.
 */
class VizoraSetupActivity : Activity() {
    private class Step(val title: String, val hint: String, val done: () -> Boolean, val open: () -> Unit)

    private lateinit var steps: List<Step>
    private val marks = mutableListOf<TextView>()
    private val tried = mutableSetOf<Int>()
    private var auto = false
    private var finished = false
    private lateinit var summary: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // start on boot, so the service comes back after a power cut
        getSharedPreferences(KEY_SHARED_PREFERENCES, MODE_PRIVATE).edit().putBoolean(KEY_START_ON_BOOT_OPT, true).apply()
        steps = listOf(
            Step("הצגה מעל אפליקציות אחרות", "להדליק את המתג ולחזור אחורה", { overlayOk() }, { overlay() }),
            Step("צילום המסך", "לסמן \"אל תציג שוב\" אם יש, ולבחור \"התחל עכשיו\"", { MainService.isReady }, { capture() }),
            Step("חיסכון בסוללה", "לאשר, כדי שאנדרואיד לא יסגור את השירות", { batteryOk() }, { battery() }),
            Step("שליטה במסך (נגישות)", "לבחור VIZORA Remote, להדליק ולחזור אחורה", { InputService.isOpen }, { accessibility() }),
        )
        setContentView(layout())
        say("נפתח מסך ההגדרה")
    }

    override fun onResume() {
        super.onResume()
        refresh()
        if (auto) summary.postDelayed({ goNext() }, 900)
        tick()
    }

    // the approvals change outside this screen (the service starts a moment after the capture is approved)
    private fun tick() {
        summary.postDelayed({ if (!isFinishing) { refresh(); tick() } }, 1500)
    }

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun text(s: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = s; textSize = size; setTextColor(color); if (bold) setTypeface(typeface, Typeface.BOLD)
        gravity = Gravity.START
    }

    private fun layout(): View {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            setPadding(dp(28), dp(24), dp(28), dp(24))
        }
        col.addView(text("הגדרת שליטה מרחוק - VIZORA", 26f, Color.WHITE, true))
        col.addView(text("המכשיר מנוהל על ידי VIZORA. כדי לאפשר תמיכה מרחוק צריך לאשר כאן 4 דברים, פעם אחת. לוחצים \"התחלה\", ובכל מסך שנפתח מאשרים וחוזרים אחורה.", 16f, Color.rgb(200, 196, 230)).apply { setPadding(0, dp(8), 0, dp(16)) })
        col.addView(Button(this).apply {
            text = "התחלה"; textSize = 20f; isAllCaps = false
            setOnClickListener { auto = true; tried.clear(); say("נלחץ התחלה"); goNext() }
        })
        steps.forEachIndexed { i, s ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                layoutDirection = View.LAYOUT_DIRECTION_RTL
                setPadding(0, dp(14), 0, 0)
            }
            val mark = text("○", 26f, Color.rgb(150, 146, 180), true).apply { setPadding(0, 0, 0, 0); minWidth = dp(40) }
            marks.add(mark)
            val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(10), 0, dp(10), 0) }
            texts.addView(text("${i + 1}. ${s.title}", 18f, Color.WHITE, true))
            texts.addView(text(s.hint, 14f, Color.rgb(170, 166, 200)))
            row.addView(mark)
            row.addView(texts, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(Button(this).apply {
                text = "פתיחה"; isAllCaps = false
                setOnClickListener { tried.add(i); openStep(i) }
            })
            col.addView(row)
        }
        summary = text("", 16f, Color.rgb(255, 214, 120), true).apply { setPadding(0, dp(18), 0, dp(8)) }
        col.addView(summary)
        col.addView(Button(this).apply {
            text = "סיום"; isAllCaps = false
            setOnClickListener { report(); finish() }
        })
        return ScrollView(this).apply { setBackgroundColor(Color.rgb(20, 18, 43)); addView(col) }
    }

    private fun refresh() {
        steps.forEachIndexed { i, s ->
            val ok = try { s.done() } catch (_: Exception) { false }
            marks[i].text = if (ok) "✓" else "○"
            marks[i].setTextColor(if (ok) Color.rgb(90, 220, 140) else Color.rgb(150, 146, 180))
        }
        if (steps.all { try { it.done() } catch (_: Exception) { false } } && !finished) {
            finished = true
            summary.text = "הכל מאושר. השליטה מרחוק מוכנה, והיא תעלה לבד גם אחרי כיבוי."
            report()
            summary.postDelayed({ if (!isFinishing) finish() }, 4000)
        }
    }

    private fun goNext() {
        if (finished) return
        val i = steps.indices.firstOrNull { !steps[it].done() && it !in tried }
        if (i == null) {
            auto = false
            summary.text = "נשארו שלבים בלי ✓: לוחצים \"פתיחה\" לידם ומאשרים."
            report()
            return
        }
        tried.add(i)
        openStep(i)
    }

    private fun openStep(i: Int) {
        say("שלב ${i + 1}: ${steps[i].title}")
        try {
            steps[i].open()
        } catch (e: Exception) {
            Log.w("VIZORA", "setup step ${i + 1}: ${e.message}")
            say("שלב ${i + 1}: אין מסך כזה במכשיר (${e.javaClass.simpleName})")
            if (auto) summary.postDelayed({ goNext() }, 300)
        }
    }

    private fun overlayOk() = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this)
    private fun overlay() {
        try {
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        }
    }

    private fun capture() {
        // the same request RustDesk's "Start service" makes; on approval it starts the service itself
        startActivity(Intent(this, PermissionRequestTransparentActivity::class.java).apply { action = ACT_REQUEST_MEDIA_PROJECTION })
    }

    private fun batteryOk(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        return (getSystemService(Context.POWER_SERVICE) as PowerManager).isIgnoringBatteryOptimizations(packageName)
    }
    private fun battery() {
        try {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun accessibility() = startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))

    private fun report() {
        val st = steps.mapIndexed { i, s -> "${i + 1}" + (if (try { s.done() } catch (_: Exception) { false }) "✓" else "✗") }.joinToString(" ")
        say("מצב: $st")
    }

    private fun say(msg: String) {
        try {
            val i = Intent("com.vizora.player.REMOTE_ID")
            i.setPackage("com.vizora.player")
            i.putExtra("setup", msg)
            sendBroadcast(i)
        } catch (_: Exception) {}
    }
}
