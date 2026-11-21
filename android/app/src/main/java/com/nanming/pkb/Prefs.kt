package com.nanming.pkb

import android.content.Context
import java.util.UUID

class Prefs(context: Context) {

    private val sp = context.getSharedPreferences("pkb", Context.MODE_PRIVATE)

    var url: String
        get() = sp.getString("url", "") ?: ""
        set(value) = sp.edit().putString("url", value).apply()

    var baseUrl: String
        get() = sp.getString("base", "") ?: ""
        set(value) = sp.edit().putString("base", value).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(value) = sp.edit().putString("token", value).apply()

    var deviceId: String
        get() {
            val existing = sp.getString("device_id", "") ?: ""
            if (existing.isNotEmpty()) return existing
            val created = "pkb-app-" + UUID.randomUUID().toString()
            sp.edit().putString("device_id", created).apply()
            return created
        }
        set(value) = sp.edit().putString("device_id", value).apply()

    var lastActivate: Int
        get() = sp.getInt("last_activate", 0)
        set(value) = sp.edit().putInt("last_activate", value).apply()
}
