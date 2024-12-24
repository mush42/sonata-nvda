import re
import json
import os
import unicodedata

from .helpers import CFG_DIRECTORY
#CFG_DIRECTORY = "/Users/galbert/workspace/dra/eastern-armenian-nvda/addon/synthDrivers/eastern_armenian_voices/cfg"

class PhoneticProcessingEngine:
    """ Class for describing a "phonetic" processing engine """
    # Define variables
    _excluding_pattern = None
    _general_patterns = None
    _exceptions = None

    def __init__(self, configuration, contextProcessing = False):
        if (contextProcessing):
            self._excluding_pattern = "^$"
            self._exceptions = []
            self._general_patterns = configuration["general_patterns"]
        else:
            self._excluding_pattern = configuration["excluding_pattern"]
            self._exceptions = configuration["exceptions"]
            self._general_patterns = configuration["general_patterns"]

class PhoneticEngine:
    """
        Class for preprocessing Armenian letters through the "phonetic"
        alphabet.
    """
    # Define variables
    _is_initialized = None
    _cfg_file = None
    _engine_cfg = os.path.join(CFG_DIRECTORY, "phonetic_processing_configuration.json")
    _initial_engine = None
    _case_sensitive_engines = None
    _context_sensitive_engines = None
    _engines = None
    _vocabulary_all = None
    _vocabulary_processed = None

    def load_configuration(self):
        print(f"Loading configuration from: {self._engine_cfg}")
        self._cfg_file = self._engine_cfg
        self._engines = []
        self._case_sensitive_engines = []
        self._context_sensitive_engines = []
        with open(self._cfg_file,  'r', encoding='utf-8') as json_file:
            j = json.load(json_file)
            self._initial_engine = PhoneticProcessingEngine(j["initial"])

            for engine in j["case_sensitive_engines"]:
                self._case_sensitive_engines.append(PhoneticProcessingEngine(j[engine]))
            for engine in j["context_sensitive_engines"]:
                self._context_sensitive_engines.append(PhoneticProcessingEngine(j[engine], contextProcessing = True))
            for engine in j["engines"]:
                self._engines.append(PhoneticProcessingEngine(j[engine]))
            self._vocabulary_all = j["vocabulary_all"]
            self._vocabulary_processed = j["vocabulary_processed"]

    def process_engine_text_internal(self, text, engine):
        # Excluding exception handling
        if re.match(engine._excluding_pattern, text):
            return text

        # Exception case handling: replace one match and exit
        for exception in engine._exceptions:
            if re.match(exception[0], text):
                return re.sub(exception[0], exception[1], text, exception[2])

        # General pattern handling: replace all matches
        for pattern in engine._general_patterns:
            text = re.sub(pattern[0], pattern[1], text, pattern[2])
        return text

    def process_engine_text(self, text, engine):
        result = ""
        for word in text.split():
            result += " "
            result += self.process_engine_text_internal(word, engine)
        return result.strip()

    def process_context_engine_text(self, text, engine):
        return self.process_engine_text_internal(text, engine)

    def remove_non_supported_characters_before_processing(self, text):
        text = re.sub(u"[^{}]+".format(self._vocabulary_all), " ", text)
        text = re.sub('\s+',' ', text) # remove double spaces, tabs, new lines.
        text = text.strip()
        return text

    def remove_non_supported_characters_after_processing(self, text):
        text = re.sub(u"[^{}]+".format(self._vocabulary_processed), " ", text)
        text = re.sub('\s+',' ', text)
        text = text.strip()
        return text

    def remove_spaces(self, text):
        return re.sub('\s+',' ', text).strip()

    def process(self, text, production=True):
        text = ''.join(char for char in unicodedata.normalize('NFD', text)
                       if unicodedata.category(char) != 'Mn')  # Strip accents

        # Process the initial engine.
        text = self.process_engine_text(text, self._initial_engine)

        # Process case-sensitive engines.
        for engine in self._case_sensitive_engines:
            text = self.process_engine_text(text, engine)

        # Lowercase.
        text = text.lower()

        # Process context engines.
        for engine in self._context_sensitive_engines:
            text = self.process_context_engine_text(text, engine)

        # Process case-free engines.
        for engine in self._engines:
            text = self.process_engine_text(text, engine)

        text = self.remove_spaces(text) # remove double spaces, tabs, new lines.

        return text

    def __init__(self):
        self.load_configuration()

if __name__ == '__main__':
    engine = PhoneticEngine()
    print(engine.process("abc"))
