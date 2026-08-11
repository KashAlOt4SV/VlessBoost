# VLESS Boost

Split-tunnel бустер для **Windows** и **Android**: выбранный трафик идёт через ваш `vless://` VPN (sing-box), остальное — напрямую.

Идея как у игровых бустеров: включаете Discord, YouTube, браузер или конкретные приложения на телефоне — ускоряете/обходите блокировки только их, без полного VPN на весь ПК или телефон.

Версия: **1.1.0**

## Что умеет

### Windows (десктоп)
- Каталог сервисов с переключателями (Discord, YouTube, соцсети, AI, игры и др.)
- Маршрутизация по **процессам**, **доменам** и **IP**
- Защита рабочих сайтов (Microsoft / Teams / Office и т.п.) — они остаются direct
- Обновление списков из v2fly и Antifilter Community
- Свои домены и процессы
- TUN через **sing-box** (нужны права администратора)
- Трей при активном бусте
- Вкладки **Логи** и **Обновление приложения**

### Android (APK)
- Per-app VPN: выбираете приложения — только они идут через VLESS
- Быстрые пресеты сайтов (Discord, YouTube, Telegram, Instagram…)
- Экран **Логи** (live из libbox) для отладки
- Кнопка **Обновить** (проверка `version.json` + скачивание APK)
- Движок: **sing-box libbox** (VpnService + TUN)

## Структура репозитория

```
vless-split/
├── main.py / app/          # Windows-приложение (Python + customtkinter)
├── run.bat / build.bat     # запуск и сборка exe
├── dist/                   # собранный VLESS-Boost.exe (после build)
├── android/                # Android-проект (Kotlin)
│   └── VLESS-Boost.apk     # готовый debug APK после сборки
└── update/version.json     # шаблон манифеста OTA-обновлений
```

## Windows

### Запуск из исходников

```bat
cd C:\Users\shaya\Projects\vless-split
python -m pip install -r requirements.txt
run.bat
```

Нужны **права администратора** (TUN).

1. **Настройки** — вставьте `vless://` ссылку  
2. **Сервисы** — включите нужные пресеты  
3. **Обновление списков** — по желанию подтяните remote-листы  
4. Кнопка **BOOST**  
5. Перезапустите Discord / браузер после включения  

### Сборка exe

```bat
build.bat
```

Результат: `dist\VLESS-Boost.exe` (запрос UAC при старте).

## Android

### Готовый APK

После сборки файл лежит здесь:

`android\VLESS-Boost.apk`

Установка: скопировать на телефон → разрешить установку из неизвестных источников → установить.

### Сборка APK

Нужны JDK 17 и Android SDK (platform 34).

```bat
cd android
gradlew.bat assembleDebug
```

APK: `android\app\build\outputs\apk\debug\app-debug.apk`  
(копия удобного имени: `android\VLESS-Boost.apk`)

### Как пользоваться

1. Вставить `vless://` ссылку  
2. **Выбрать приложения** (включая системные вроде YouTube)  
3. По желанию включить пресеты сайтов  
4. **Включить** → полностью закрыть и снова открыть выбранные приложения  
5. Если что-то не грузится — открыть **Логи** и скопировать вывод  

## Обновления по воздуху (просто)

Оба клиента умеют проверять манифест `version.json`:

```json
{
  "android": {
    "versionCode": 2,
    "versionName": "1.1.0",
    "url": "https://…/VLESS-Boost.apk"
  },
  "windows": {
    "version": "1.1.0",
    "url": "https://…/VLESS-Boost.exe"
  }
}
```

URL манифеста: `https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json`  
После публикации релиза положите APK/EXE в GitHub Releases и обновите ссылки в `update/version.json`.

### Android: libbox.aar

Файл `android/app/libs/libbox.aar` (~115 МБ) в git не входит. Перед сборкой APK скачайте его, например:

```powershell
New-Item -ItemType Directory -Force -Path android\app\libs | Out-Null
Invoke-WebRequest -Uri "https://github.com/Leadaxe/sing-box-lx/releases/download/v1.14.0-lx.22/libbox.aar" -OutFile android\app\libs\libbox.aar
```

(проверьте актуальный URL релиза Leadaxe / sing-box libbox при необходимости)

## Замечания

- Reality: параметр `pqv` (post-quantum) sing-box не поддерживает — его нужно убирать из ссылки  
- На Windows пресет «весь браузер» гоняет весь Chrome/Edge через VPN; для YouTube обычно хватает доменного пресета  
- Antifilter Community — широкий список; включайте осознанно  
- Android: после включения VPN всегда перезапускайте выбранные приложения  

## Стек

| Платформа | UI | Ядро |
|-----------|----|------|
| Windows   | Python, customtkinter | sing-box TUN |
| Android   | Kotlin, Material 3 | libbox (sing-box) VpnService |
