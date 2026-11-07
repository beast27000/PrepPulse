"""Request-local pseudonymization before external inference; never persist the map.

Original records stay local. This reduces direct identifier disclosure, but is not
anonymization of a medical history and cannot redact speech before transcription.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlparse


class PrivacyUnavailable(RuntimeError):
    """Fail closed if the identity registry cannot be read."""


def local_endpoint(url: str) -> bool:
    host = urlparse(str(url)).hostname or ""
    if host in {"localhost", "host.docker.internal"}:
        return True
    try:
        address = ip_address(host)
        return address.is_loopback or address.is_private
    except ValueError:
        return False


def load_identifiers():
    # A fresh projection also covers patients registered moments before analysis.
    # Do not instantiate API stores/indexes or load credentials/password hashes.
    from pymongo import MongoClient
    from preppulse_api.config import MONGO_DB, MONGO_URI

    fields = {key: 1 for key in ("name", "dob", "patient_id", "external_aliases",
        "phone", "phone_number", "email", "address", "contact", "contact_details")}
    fields["_id"] = 0
    try:
        with MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000) as client:
            return list(client[MONGO_DB].patients.find({}, fields))
    except Exception:
        raise PrivacyUnavailable("Patient privacy registry unavailable; external AI request blocked") from None


class PrivacyFilter:
    def __init__(self, identities=None):
        self.mapping = {}
        self.reverse = {}
        self.known = {}
        for person in load_identifiers() if identities is None else identities:
            name = str(person.get("name") or "").strip()
            if name:
                self.known[name] = "NAME"
                self.known[name.replace("_", " ")] = "NAME"
                # Partial names in narrative text and identifying filenames.
                for part in re.split(r"[\s_]+", name):
                    if len(part) >= 4:
                        self.known[part] = "NAME"
            for field, kind in (("patient_id", "ID"), ("external_aliases", "ID"),
                                ("phone", "CONTACT"), ("phone_number", "CONTACT"),
                                ("email", "CONTACT"), ("address", "CONTACT"),
                                ("contact", "CONTACT"), ("contact_details", "CONTACT")):
                self._known_values(person.get(field), kind)
            dob = str(person.get("dob") or "")[:10]
            if dob:
                self.known[dob] = "DOB"
                try:
                    born = datetime.strptime(dob, "%Y-%m-%d")
                    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y",
                                "%d %B %Y", "%d-%B-%Y"):
                        self.known[born.strftime(fmt)] = "DOB"
                        self.known[born.strftime(fmt).lstrip("0")] = "DOB"
                except ValueError:
                    pass
        values = sorted((x for x in self.known if len(x) >= 3), key=len, reverse=True)
        self.pattern = re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(x) for x in values)
                                  + r")(?![^\W_])", re.IGNORECASE) if values else None

    def _known_values(self, value, kind):
        if isinstance(value, str) and len(value.strip()) >= 3:
            self.known[value.strip()] = kind
        elif isinstance(value, dict):
            for item in value.values():
                self._known_values(item, kind)
        elif isinstance(value, list):
            for item in value:
                self._known_values(item, kind)

    def token(self, value, kind):
        identity = (kind, value)
        if identity not in self.reverse:
            marker = "PPPRIV" + kind + secrets.token_hex(8).upper() + "END"
            self.mapping[marker] = value
            self.reverse[identity] = marker
        return self.reverse[identity]

    def _text(self, text):
        if self.pattern:
            text = self.pattern.sub(lambda m: self.token(m[0], "IDENTITY"), text)
        text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
                      lambda m: self.token(m[0], "EMAIL"), text)
        text = re.sub(r"(?<!\w)(?:\+91[ -]?)?[6-9]\d{9}(?!\w)",
                      lambda m: self.token(m[0], "PHONE"), text)
        text = re.sub(r"\b(?:PRP|HCW|FAM|DOC|ADM)-[A-F0-9]{8,}\b|\bPP\d{3,}\b",
                      lambda m: self.token(m[0], "ID"), text, flags=re.IGNORECASE)
        # Identifiers present in an unregistered document or typed in free text.
        labels = r"DOB|Date of birth|Phone|Mobile|Telephone|Email|Address|Patient name|Patient|MRN|UHID|Aadhaar"
        pattern = r"(?im)\b(" + labels + r")\s*[:=]\s*([^\n\r|;,]+)"
        def labelled(match):
            value = match[2].strip()
            if "PPPRIV" in value:
                return match[0]
            # Patient lines can include clinical details; stop at the first such field.
            value = re.split(r"\s+(?=Age\b|Sex\b|HbA1c\b|has\b|with\b)", value, maxsplit=1,
                             flags=re.IGNORECASE)[0].strip()
            return match[0].replace(value, self.token(value, "LABEL"), 1) if value else match[0]
        return re.sub(pattern, labelled, text)

    def redact(self, value):
        if isinstance(value, str):
            # Preserve JSON keys (including drug 'name') and protocol shape.
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                return self._text(value)
            if isinstance(parsed, (dict, list)):
                return json.dumps(self.redact(parsed), ensure_ascii=False)
            return self._text(value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            identity_keys = {"patient_name", "full_name", "dob", "date_of_birth", "email", "phone",
                             "phone_number", "mobile", "address", "external_aliases", "patient_id"}
            return {key: self._identity_value(item) if key.casefold() in identity_keys else self.redact(item)
                    for key, item in value.items()}
        return value

    def _identity_value(self, value):
        if isinstance(value, str) and value.strip():
            return self.token(value, "IDENTITY")
        if isinstance(value, list):
            return [self._identity_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._identity_value(item) for key, item in value.items()}
        return value

    def restore(self, text):
        if not isinstance(text, str):
            return text
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(self._restore_value(parsed), ensure_ascii=False)
        return self._restore_text(text)

    def _restore_value(self, value):
        if isinstance(value, str):
            return self._restore_text(value)
        if isinstance(value, list):
            return [self._restore_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._restore_value(item) for key, item in value.items()}
        return value

    def _restore_text(self, text):
        # A single substitution prevents original text being recursively interpreted.
        return re.sub(r"PPPRIV[A-Z]+[A-F0-9]{16}END", lambda m: self.mapping.get(m[0], m[0]), text)

    def messages(self, messages):
        return [message.model_copy(update={"content": self.redact(message.content)}) for message in messages]
