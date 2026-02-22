class LanguageManager:
    STRINGS = {
        "pt": {
            "main.install": "INSTALADOR/CONFIGURAR SERVICOS",
            "main.users": "GERENCIAMENTO DE USUARIOS",
            "main.tools": "FERRAMENTAS DO SISTEMA",
            "main.about": "SOBRE",
            "main.exit": "SAIR",
            "menu.back": "VOLTAR",
            "lang.changed": "Idioma alterado com sucesso.",
        },
        "en": {
            "main.install": "INSTALLER/CONFIGURE SERVICES",
            "main.users": "USER MANAGEMENT",
            "main.tools": "SYSTEM TOOLS",
            "main.about": "ABOUT",
            "main.exit": "EXIT",
            "menu.back": "BACK",
            "lang.changed": "Language changed successfully.",
        },
    }

    def __init__(self, default_lang="pt"):
        self.current_lang = default_lang if default_lang in self.STRINGS else "pt"

    def set_language(self, lang: str):
        if lang in self.STRINGS:
            self.current_lang = lang
            return True
        return False

    def t(self, key: str, fallback: str = "") -> str:
        return self.STRINGS.get(self.current_lang, {}).get(key, fallback or key)
