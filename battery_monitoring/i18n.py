from __future__ import annotations

LANGUAGES = {"en": "English", "tr": "Türkçe", "zh": "中文", "es": "Español"}

FONTS = {"zh": "Microsoft YaHei UI"}
DEFAULT_FONT = "Segoe UI"

STRINGS = {
    "tr": {
        "menu.show": "Pilleri göster",
        "menu.quit": "Çıkış",
        "title.devices": "Cihazlar",
        "title.settings": "Ayarlar",
        "btn.refresh": "Yenile",
        "status.scanning": "Taranıyor...",
        "status.last": "Son tarama: {t}",
        "status.first": "İlk tarama yapılıyor...",
        "empty": "Henüz cihaz bulunamadı.",
        "kind.mouse": "Fare",
        "kind.keyboard": "Klavye",
        "kind.headset": "Kulaklık",
        "kind.gamepad": "Oyun kolu",
        "kind.device": "Cihaz",
        "state.charging": "Şarj oluyor",
        "state.offline": "Bağlı değil / uykuda",
        "note.voltage_charging": "Şarjdayken seviye okunamıyor",
        "set.theme": "Tema",
        "theme.dark": "Koyu",
        "theme.light": "Açık",
        "set.language": "Dil",
        "set.threshold": "Uyarı eşiği",
        "set.autostart": "Windows ile başlat",
        "set.diag": "Tanılama raporu",
        "notify.title": "Pil azaldı",
        "notify.body": "Şarja takmayı unutma.",
    },
    "en": {
        "menu.show": "Show batteries",
        "menu.quit": "Quit",
        "title.devices": "Devices",
        "title.settings": "Settings",
        "btn.refresh": "Refresh",
        "status.scanning": "Scanning...",
        "status.last": "Last scan: {t}",
        "status.first": "Running the first scan...",
        "empty": "No devices found yet.",
        "kind.mouse": "Mouse",
        "kind.keyboard": "Keyboard",
        "kind.headset": "Headset",
        "kind.gamepad": "Gamepad",
        "kind.device": "Device",
        "state.charging": "Charging",
        "state.offline": "Disconnected / asleep",
        "note.voltage_charging": "Level unavailable while charging",
        "set.theme": "Theme",
        "theme.dark": "Dark",
        "theme.light": "Light",
        "set.language": "Language",
        "set.threshold": "Alert threshold",
        "set.autostart": "Start with Windows",
        "set.diag": "Diagnostics report",
        "notify.title": "Battery low",
        "notify.body": "Don't forget to charge it.",
    },
    "zh": {
        "menu.show": "显示电量",
        "menu.quit": "退出",
        "title.devices": "设备",
        "title.settings": "设置",
        "btn.refresh": "刷新",
        "status.scanning": "正在扫描…",
        "status.last": "上次扫描：{t}",
        "status.first": "正在进行首次扫描…",
        "empty": "尚未找到设备。",
        "kind.mouse": "鼠标",
        "kind.keyboard": "键盘",
        "kind.headset": "耳机",
        "kind.gamepad": "手柄",
        "kind.device": "设备",
        "state.charging": "正在充电",
        "state.offline": "未连接 / 休眠",
        "note.voltage_charging": "充电时无法读取电量",
        "set.theme": "主题",
        "theme.dark": "深色",
        "theme.light": "浅色",
        "set.language": "语言",
        "set.threshold": "低电量提醒",
        "set.autostart": "开机自动启动",
        "set.diag": "诊断报告",
        "notify.title": "电量不足",
        "notify.body": "别忘了充电。",
    },
    "es": {
        "menu.show": "Mostrar baterías",
        "menu.quit": "Salir",
        "title.devices": "Dispositivos",
        "title.settings": "Ajustes",
        "btn.refresh": "Actualizar",
        "status.scanning": "Buscando...",
        "status.last": "Último escaneo: {t}",
        "status.first": "Realizando el primer escaneo...",
        "empty": "Aún no se encontraron dispositivos.",
        "kind.mouse": "Ratón",
        "kind.keyboard": "Teclado",
        "kind.headset": "Auriculares",
        "kind.gamepad": "Mando",
        "kind.device": "Dispositivo",
        "state.charging": "Cargando",
        "state.offline": "Desconectado / en reposo",
        "note.voltage_charging": "Nivel no disponible mientras carga",
        "set.theme": "Tema",
        "theme.dark": "Oscuro",
        "theme.light": "Claro",
        "set.language": "Idioma",
        "set.threshold": "Umbral de aviso",
        "set.autostart": "Iniciar con Windows",
        "set.diag": "Informe de diagnóstico",
        "notify.title": "Batería baja",
        "notify.body": "No olvides cargarlo.",
    },
}


class Translator:
    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in STRINGS else "en"

    def __call__(self, key: str, **kwargs) -> str:
        text = STRINGS[self.lang].get(key) or STRINGS["en"].get(key) or key
        return text.format(**kwargs) if kwargs else text

    def pct(self, level) -> str:
        if level is None:
            return "?"
        return f"%{level}" if self.lang == "tr" else f"{level}%"

    def has(self, key: str) -> bool:
        return key in STRINGS["en"]

    @property
    def font(self) -> str:
        return FONTS.get(self.lang, DEFAULT_FONT)
