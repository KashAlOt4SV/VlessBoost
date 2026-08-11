package com.vlessboost.app

data class SitePreset(
    val id: String,
    val title: String,
    val domains: List<String>,
)

object Presets {
    val all: List<SitePreset> = listOf(
        SitePreset("discord", "Discord", listOf(
            "discord.com", "discord.gg", "discordapp.com", "discordapp.net",
            "discord.media", "discordcdn.com", "discordstatus.com",
        )),
        SitePreset("youtube", "YouTube", listOf(
            "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com",
            "ggpht.com", "youtubei.googleapis.com",
        )),
        SitePreset("telegram", "Telegram", listOf(
            "telegram.org", "t.me", "telegram.me", "cdn-telegram.org",
        )),
        SitePreset("instagram", "Instagram", listOf(
            "instagram.com", "cdninstagram.com",
        )),
        SitePreset("tiktok", "TikTok", listOf(
            "tiktok.com", "tiktokcdn.com", "tiktokv.com",
        )),
        SitePreset("twitter", "X", listOf(
            "x.com", "twitter.com", "twimg.com", "t.co",
        )),
        SitePreset("openai", "ChatGPT", listOf(
            "openai.com", "chatgpt.com", "oaistatic.com",
        )),
        SitePreset("speedtest", "Speedtest", listOf(
            "speedtest.net", "ookla.com", "ooklaserver.net",
        )),
    )
}
