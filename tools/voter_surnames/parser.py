"""
Arabic text normalization and voter line parser for ISIE voter registry PDFs.
"""

import re
import unicodedata

# Regex for common polling center prefixes
CENTER_PATTERN = re.compile(
    r'\s+(م\s*[\.\s]*إ[\.\s]*|م\s+إبتدائ|م\s+إعدادي|م\s*[\.\s]*إع[\.\s]*|معهد|مركز|مدرسة|المدرسة|المعهد|دار الشباب|المركب|مكتب|روضة|القاعة|فضاء|قنصلية|سفارة|بلدية|نادي|جامع|إعدادية|فضاء|قاعة|مركب|دار الثقافة|دار)(.*)$'
)

# Arabic diacritics / tashkeel
TASHKEEL_REGEX = re.compile(r'[\u064B-\u0652\u0670\u0640]')

def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for indexing and fuzzy comparison."""
    if not text:
        return ""
    # Strip tashkeel & tatweel
    text = TASHKEEL_REGEX.sub('', text)
    # Normalize alefs
    text = re.sub(r'[إأآٱ]', 'ا', text)
    # Normalize yaa / alef maqsura
    text = re.sub(r'ى', 'ي', text)
    # Normalize taa marbuta
    text = re.sub(r'ة', 'ه', text)
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Common prefixes for compound surnames ending with الله
ALLAH_PREFIXES = {
    'ضيف', 'عطاء', 'فتح', 'جار', 'نصر', 'نعمة', 'حبيب', 'سعد', 'خير', 'لطف', 
    'رحمة', 'فضل', 'امان', 'أمان', 'هبة', 'ذكر', 'عبد', 'قدرة', 'بركة', 'نور', 
    'عزة', 'سيف', 'جاد', 'شكر', 'حفظ', 'عوض', 'خلف', 'رزق', 'فرج', 'معونة', 
    'هداية', 'عناية', 'كرم', 'جود', 'رضوان', 'مساعد', 'خليل', 'حكمة', 'اية', 
    'آية', 'ولي', 'عابد', 'حامد', 'حمد', 'نصرت', 'عصمت', 'شكرى', 'شكري'
}

# Common prefixes for compound surnames ending with الدين
DEEN_PREFIXES = {
    'شرف', 'صلاح', 'سيف', 'نور', 'بهاء', 'حسام', 'علاء', 'زين', 'تقي', 'جمال', 
    'عماد', 'كمال', 'محي', 'محيي', 'فخر', 'جلال', 'عز', 'تاج', 'بدر', 'ضياء', 
    'سراج', 'نجم', 'شمس', 'شهاب', 'غياث', 'معز', 'ظهير', 'عصام', 'امين', 'أمين', 
    'ناصر', 'معين', 'وجيه'
}


def parse_tunisian_surname(full_name: str):
    """
    Decompose Tunisian full name into first_name, patronymic, raw surname, and normalized surname.
    Accurately handles:
    - 3-word compounds ending with الله / الدين: e.g. بن ضيف الله, بن عبد الله, بن شرف الدين
    - 3-word compounds with titles/prefixes: e.g. بن الحاج علي, بن الشيخ أحمد, بن عبد الكريم
    - 2-word compounds ending with الله / الدين: e.g. ضيف الله, بنضيف الله, شرف الدين, سيف الدين
    - 2-word prefixes: بن ..., بو ..., بل ..., عبد ..., آل ..., سيدي ..., ولد ...
    - Single word surnames
    """
    full_name = full_name.strip()
    words = full_name.split()
    if not words:
        return "", "", "", ""
    
    if len(words) == 1:
        return words[0], "", words[0], normalize_arabic(words[0])
    
    surname = None
    remaining = None

    # Case A: 3-word compounds ending with الله or الدين (e.g. بن ضيف الله, بن شرف الدين, بن عبد الله)
    if len(words) >= 4 and words[-3] in ['بن', 'ابن', 'بو', 'بل', 'بنت'] and words[-1] in ['الله', 'الدين']:
        surname = f"{words[-3]} {words[-2]} {words[-1]}"
        remaining = words[:-3]

    # Case B: 3-word compounds with honorifics or عبد (e.g. بن الحاج علي, بن الشيخ أحمد, بن عبد الكريم)
    elif len(words) >= 4 and words[-3] in ['بن', 'ابن'] and (words[-2] in ['الحاج', 'الشيخ', 'سيدي', 'عبد']):
        surname = f"{words[-3]} {words[-2]} {words[-1]}"
        remaining = words[:-3]

    # Case C: 2-word compounds ending with الله or الدين (e.g. ضيف الله, بنضيف الله, شرف الدين)
    elif len(words) >= 3 and words[-1] in ['الله', 'الدين']:
        surname = f"{words[-2]} {words[-1]}"
        remaining = words[:-2]

    # Case D: 2-word prefix compounds (e.g. بن علي, بو عزيز, عبد الكافي, آل ثاني, سيدي بوبكر)
    elif len(words) >= 3 and words[-2] in ['بن', 'ابن', 'بنت', 'بو', 'عبد', 'ولد', 'آل', 'سيدي', 'بل']:
        surname = f"{words[-2]} {words[-1]}"
        remaining = words[:-2]

    # Fallback: single word surname
    else:
        surname = words[-1]
        remaining = words[:-1]

    first_name = remaining[0] if remaining else ""
    patronymic = " ".join(remaining[1:]) if len(remaining) > 1 else ""
    surname_norm = normalize_arabic(surname)
    
    return first_name, patronymic, surname, surname_norm


def parse_latin_surname(name: str):
    """
    Decompose Latin full name into surname and normalized surname.
    Handles compound Latin prefixes: Ben, Bou, Bel, Abdel, Abd, Ait, Ould, De.
    """
    words = name.strip().split()
    if not words:
        return "", ""
    if len(words) >= 3 and words[-2].upper() in ['BEN', 'BOU', 'BEL', 'ABDEL', 'ABD', 'AIT', 'OULD', 'DE']:
        sn = f"{words[-2].title()} {words[-1].title()}"
    elif len(words) >= 4 and words[-3].upper() in ['BEN', 'BOU'] and words[-2].upper() in ['ABDEL', 'ABD']:
        sn = f"{words[-3].title()} {words[-2].title()} {words[-1].title()}"
    else:
        sn = words[-1].title()
    return sn, sn.upper()


def parse_voter_line(line: str):
    """
    Parse a single voter row from the PDF into (cin_last3, full_name, polling_center).
    Expected line format:
    [CIN last 3 digits] [Full Name] [Polling Center]
    """
    line = line.strip()
    if not line:
        return None
    
    parts = line.split(maxsplit=1)
    if len(parts) < 2:
        return None
    
    cin = parts[0]
    if not cin.isdigit() or len(cin) > 5:
        return None
    
    rest = parts[1]
    m = CENTER_PATTERN.search(rest)
    if m:
        name = rest[:m.start()].strip()
        center = (m.group(1) + m.group(2)).strip()
    else:
        # Fallback if center prefix not matched cleanly
        subwords = rest.split()
        if len(subwords) >= 3:
            # Assume last 2-3 words are center
            name = " ".join(subwords[:-2])
            center = " ".join(subwords[-2:])
        else:
            name = rest
            center = ""
            
    return cin, name, center
