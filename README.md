# VEIL · AmneziaWG 3.1

Актуальная версия Windows — **2.0.2**. Нативный интерфейс Qt, официальный транспорт AmneziaWG 3.1 и выборочная маршрутизация по процессам, доменам и IP. Исправлено отключение туннеля при ошибке сертификата HTTPS-диагностики: в сборку включены корневые сертификаты Mozilla, а состояние AWG проверяется независимо. Старое описание ниже относится к прежней версии и Android.

**[Скачать VEIL 2.0.2 для Windows x64](https://github.com/KashAlOt4SV/VlessBoost/releases/tag/v2.0.2)**. Распакуйте весь ZIP, завершите старый клиент через трей → Выход и запустите VEIL.exe. Для перехода с VLESS нужен профиль AmneziaWG 3.1; автоматического преобразования ключей нет.

**[Инструкция со скриншотами: получить .conf у «Вездехода» и настроить подключение](docs/QUICKSTART-RU.md)** · **[Скачать инструкцию в PDF](https://github.com/KashAlOt4SV/VlessBoost/releases/download/v2.0.1/VEIL-2.0.1-Quickstart-RU.pdf)**

**Готовая сборка:** `dist/VEIL/VEIL.exe`. Распространяйте всю папку `VEIL`, включая `_internal` и `bin`. Сборка запрашивает права администратора для сетевых адаптеров. Пересборка: `build.bat`.

1. Откройте **Настройки → Импорт .conf** и выберите экспортированный профиль AmneziaWG 3.1. Можно вставить .conf или vpn://, если ссылка содержит вложенный AWG .conf.
2. Выберите приложения и сервисы в **Маршрутизации**. Добавляйте свои .exe, домены и обновляйте IP-листы при необходимости.
3. Нажмите **Подключить**. Состояние «Вы подключены» появляется после HTTPS-проверки через AWG. Если не проходит именно проверка сертификата, допустимо отдельное подтверждение свежего handshake AWG и полученных данных: клиент покажет предупреждение, а HTTPS-отклик останется недоступным. Непроверенный TLS-сеанс не принимается. Правила меняются со следующего подключения; при необходимости перезапустите выбранные приложения.

**VLESS-ссылка не конвертируется в AWG:** нужен отдельный профиль совместимого сервера. Поддерживаются один Interface, один Peer, IPv4 Address, HeaderProtectionKey и S1–S4 ≥ 12. Команды PreUp/PostUp запрещены. Параметры 3.1, включая диапазоны таймеров, передаются официальному runtime. Если профиль не предоставляет IPv6-туннель, выбранный IPv6-трафик отклоняется; обычные доменные подключения используют IPv4.

Сетевой транспорт — официальный [AmneziaWG Windows 3.1.0](https://github.com/amnezia-vpn/amneziawg-windows-client/releases/tag/3.1.0). Служба `AmneziaWGTunnel$VEIL-AWG` работает с `Table=off`, без захвата системного DNS. Локальный sing-box 1.11.15 классифицирует трафик и привязывает выбранные соединения к адаптеру AWG; остальное — к исходному интерфейсу. VLESS-outbound в новом Windows-клиенте не используется. CLI службы описан в [официальной документации](https://github.com/amnezia-vpn/amneziawg-windows-client/blob/master/docs/enterprise.md).

Ключи в `%LOCALAPPDATA%/VLESS-Boost/settings.json` защищены пользовательским DPAPI; служебный .conf.dpapi — машинным DPAPI и ACL для SYSTEM/Administrators. Сохранена прежняя папка настроек для миграции выбранных сервисов. Закрытие окна по умолчанию скрывает его в трей; **Выход** в трее отключает туннель и завершает процесс.

Экраны постоянно находятся в QStackedWidget. Сеть и запуск служб выполняются в фоне. Полнооконной прозрачности нет; анимации переключателей и подсветки занимают 120–140 мс. В свёрнутом окне индикатор останавливается, графические проверки пропускаются. Очередь журнала, документ и файлы логов ограничены. HTTPS-отклик включает TCP/TLS/HTTP и не является игровым ping; скорость вычисляется по реальным RX-счётчикам AWG. Демонстрационные метрики не подставляются.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepare-runtime.ps1
# Затем run.bat; в готовой сборке оба runtime уже рядом с EXE.
```

Проверки:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py --self-check docs\native-check.json
.\.venv\Scripts\python.exe tools\render-preview.py
```

`--self-check` проверяет нативные окна, фонового работника и восстановление развёрнутого состояния без подключения к сети и сохранения настроек. Скриншоты — `docs/previews/`. Подключение к пользовательскому серверу требует настоящего AWG-профиля; здесь оно не проверялось. **Android пока остаётся на VLESS/libbox**. Старый OTA-механизм выключен в Windows, чтобы он не вернул прежний EXE.

---

## Архивное описание VLESS / Android

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
