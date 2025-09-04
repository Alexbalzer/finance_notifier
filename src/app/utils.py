

def mask_secret(s: str, keep: int = 1) -> str:
    """Maskiert sensible Strings für Logging-Ausgaben."""
    if not s:
        #  Gib "(unset)" zurück, falls der String leer oder None ist
        return "(unset)"
    # Falls die Länge > keep * 2 ist, behalte jeweils die ersten/letzten
    #       'keep' Zeichen und ersetze die Mitte durch eine Ellipse
    s = str(s)
    if len(s) <= keep * 2:
        return s[0] + "..." + (s[-1] if len(s) > 1 else "")
    return s[:keep] + "..." + s[-keep:] 

# Andernfalls gib den ersten und letzten Buchstaben mit Ellipse dazwischen aus
