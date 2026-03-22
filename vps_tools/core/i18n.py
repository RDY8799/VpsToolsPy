import json
import os


class LanguageManager:
    def __init__(self, default_lang="pt", strings_path=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.strings_path = strings_path or os.path.join(base_dir, "i18n", "strings.json")
        self.STRINGS = self._load_strings()
        self.current_lang = default_lang if default_lang in self.STRINGS else "pt"

    def _load_strings(self):
        try:
            with open(self.strings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
        return {
            "pt": {},
            "en": {},
        }

    def available_languages(self):
        return sorted(self.STRINGS.keys())

    def _pairs_map(self, lang: str):
        data = self.STRINGS.get(lang, {})
        pairs = data.get("__pairs__", {})
        return pairs if isinstance(pairs, dict) else {}

    def set_language(self, lang: str):
        if lang in self.STRINGS:
            self.current_lang = lang
            return True
        return False

    def t(self, key: str, fallback: str = "") -> str:
        current = self.STRINGS.get(self.current_lang, {})
        if key in current:
            return current[key]
        default_pt = self.STRINGS.get("pt", {})
        if key in default_pt:
            return default_pt[key]
        return fallback or key

    def t_pair(self, pt: str, en: str = "") -> str:
        key = pt or en
        if not key:
            return ""
        current_pairs = self._pairs_map(self.current_lang)
        if key in current_pairs:
            return current_pairs[key]
        pt_pairs = self._pairs_map("pt")
        if key in pt_pairs:
            return pt_pairs[key] if self.current_lang != "en" or not en else en
        return en if self.current_lang == "en" and en else pt
