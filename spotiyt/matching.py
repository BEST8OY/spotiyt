import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Tuple, Dict, Any, Optional

VERSION_PATTERNS = [
    r'[\s\-–—\(\[\{]*(?:\d{4}\s+)?Remaster(?:ed)?(?:\s+Version)?(?:\s+\d{4})?[\s\)\]\}]*$',
    r'[\s\-–—\(\[\{]*(?:Digital\s+Remaster|20\d\d\s+Remaster|19\d\d\s+Remaster|Anniversary\s+Remaster|Remaster)[\s\)\]\}]*$',
    r'[\s\-–—\(\[\{]*(?:\d+th|\d+st|\d+nd|\d+rd)\s+Anniversary(?:\s+Edition|\s+Mix|\s+Version)?[\s\)\]\}]*$',
    r'[\s\-–—\(\[\{]*(?:Radio\s+Edit|Single\s+Version|Original\s+Mix|Album\s+Version|Extended\s+Mix|Extended\s+Version|Explicit|Clean|Stereo|Mono)[\s\)\]\}]*$',
    r'[\s\-–—\(\[\{]*(?:feat\.|ft\.|featuring|with)\s+.*?[\)\]\}]?$',
    r'\s+feat\.?\s+\S+.*$',
    r'\s+ft\.?\s+\S+.*$',
]

YOUTUBE_NOISE = [
    r'[\s\-–—\(\[\{]*(?:Official\s+(?:Music\s+Video|Music\s+Audio|Video|Audio|HD\s+Video|4K\s+Video|Visualizer|Visualiser))[\s\)\]\}]*$',
    r'[\s\-–—\(\[\{]*(?:Official\s+Lyric\s+Video|Official\s+Lyrics|Lyric\s+Video|Lyrics|Visualizer|Visualiser|Audio|Audio\s+Track)[\s\)\]\}]*$',
    r'[\s\-–—\(\[\{]*(?:HD|HQ|4K|Official|Clip\s+Officiel|Video\s+Oficial|Music\s+Video)[\s\)\]\}]*$',
]

ALBUM_STRIP_PATTERNS = [
    r'[\s\-–—\(\[\{].*?(?:Deluxe|Remaster|Edition|Live|Anniversary).*?[\)\]\}]?$',
    r'[\s\-–—]+.*?(?:Deluxe|Remaster|Edition|Live|Anniversary).*?$',
]

TRACK_NUM_PREFIX = r'^\s*\d{1,3}[\.\s\-–—]+\s*'


def normalize_unicode(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize('NFKD', s)
    s = s.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2013', '-').replace('\u2014', '-').replace('\u2015', '-').replace('\u2212', '-')
    s = s.replace('\u2026', '...')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s


def clean(s: str) -> str:
    if not s:
        return ""
    s = normalize_unicode(s).lower().strip()
    s = re.sub(r'\s*(feat\.|ft\.|featuring|with|w/)\s*', ' ', s)
    for ch in [';', '-', '–', '—', '(', ')', '[', ']', '{', '}', '+', '*', '&', '/', '\\', '|', ':', ',', '!', '?', '"', '`', '~', '_', '«', '»', '•']:
        s = s.replace(ch, ' ')
    s = s.replace("'", '')
    s = s.replace('.', '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def strip_version(title: str) -> str:
    if not title:
        return ""
    title = normalize_unicode(title)
    title = re.sub(TRACK_NUM_PREFIX, '', title)
    changed = True
    while changed:
        prev = title
        for p in VERSION_PATTERNS:
            title = re.sub(p, '', title, flags=re.IGNORECASE).strip()
        for p in YOUTUBE_NOISE:
            title = re.sub(p, '', title, flags=re.IGNORECASE).strip()
        changed = (prev != title)
    return title.strip()


def strip_parens(title: str) -> str:
    if not title:
        return ""
    s = re.sub(r'\s*[\(\[\{].*?[\)\]\}]\s*', ' ', title)
    return s.strip()


def strip_album_edition(album: str) -> str:
    if not album:
        return ""
    for p in ALBUM_STRIP_PATTERNS:
        album = re.sub(p, '', album, flags=re.IGNORECASE)
    return album.strip()


def normalize_title(name: str) -> str:
    return clean(strip_version(name))


def word_ratio(s1: str, s2: str) -> float:
    w1 = s1.split()
    w2 = s2.split()
    if not w1 and not w2:
        return 1.0
    if not w1 or not w2:
        return 0.0
    seq_score = SequenceMatcher(None, w1, w2).ratio()
    s1_set, s2_set = set(w1), set(w2)
    intersection = s1_set & s2_set
    jaccard = len(intersection) / len(s1_set | s2_set) if s1_set | s2_set else 0.0
    return max(seq_score, jaccard)


def _normalize_single_artist(name: str) -> Tuple[str, str]:
    c = clean(name)
    c_no_the = re.sub(r'^the\s+', '', c).strip()
    return c, c_no_the


def _split_artists(s: str) -> List[Tuple[str, str]]:
    if not s:
        return []
    s_norm = normalize_unicode(s)
    names = re.split(r'\s*[;,/\\|]\s+|\s+&\s+|\s+and\s+|\s+feat\.?\s+|\s+ft\.?\s+|\s+featuring\s+|\s+with\s+|\s+w/\s+|\s+[xX]\s+|\s+vs\.?\s+|\s+pres\.?\s+|\s+presents\s+', s_norm, flags=re.IGNORECASE)
    result = []
    for n in names:
        n_clean, n_no_the = _normalize_single_artist(n)
        if n_clean:
            result.append((n_clean, n_no_the))
    return result


def _artist_matches(a1_tuple: Tuple[str, str], a2_tuple: Tuple[str, str]) -> bool:
    a1, a1_nt = a1_tuple
    a2, a2_nt = a2_tuple
    if a1 == a2 or a1_nt == a2_nt or a1 == a2_nt or a1_nt == a2:
        return True
    if word_ratio(a1_nt, a2_nt) >= 0.75 or word_ratio(a1, a2) >= 0.75:
        return True
    if len(a1_nt) >= 3 and len(a2_nt) >= 3:
        if a1_nt in a2_nt or a2_nt in a1_nt:
            return True
    flat1 = a1_nt.replace(" ", "")
    flat2 = a2_nt.replace(" ", "")
    if flat1 and flat2 and SequenceMatcher(None, flat1, flat2).ratio() >= 0.8:
        return True
    return False


def _artist_ratio(track_artists: str, result_artists: str) -> float:
    track_list = _split_artists(track_artists)
    result_list = _split_artists(result_artists)
    if not result_list or not track_list:
        return 0.0

    primary_matches = _artist_matches(track_list[0], result_list[0])

    matched_results = sum(1 for r in result_list if any(_artist_matches(r, t) for t in track_list))
    matched_tracks = sum(1 for t in track_list if any(_artist_matches(t, r) for r in result_list))

    score = max(matched_results / len(result_list), matched_tracks / len(track_list))
    if primary_matches:
        score = max(score, 0.75)
    return score


def join_artist_names(artist_list: List[Dict[str, str]]) -> str:
    return ", ".join(a["name"] for a in artist_list if "name" in a)


def build_query(track: Dict[str, Any]) -> str:
    parts = [track['name'], track['artists']]
    album = strip_album_edition(track.get('album', ''))
    if album:
        parts.append(album)
    return ' '.join(parts)


def _album_matches(track: Dict[str, Any], result: Dict[str, Any]) -> bool:
    expected = track.get('album', '')
    if not expected:
        return True
    actual = (result.get('album') or {}).get('name', '')
    if not actual:
        return True
    return word_ratio(clean(expected), clean(actual)) >= 0.5


def match_score(track: Dict[str, Any], result: Dict[str, Any]) -> float:
    track_title_norm = normalize_title(track['name'])
    result_title_norm = normalize_title(result.get('title', ''))

    title_score = word_ratio(track_title_norm, result_title_norm)

    track_base = normalize_title(strip_parens(track['name']))
    result_base = normalize_title(strip_parens(result.get('title', '')))
    if track_base and result_base:
        base_score = word_ratio(track_base, result_base)
        title_score = max(title_score, base_score)

    result_artists_str = join_artist_names(result.get('artists', []))
    artist_score = _artist_ratio(track['artists'], result_artists_str)

    track_artists_split = _split_artists(track['artists'])
    for t_clean, t_no_the in track_artists_split:
        if (t_clean and t_clean in result_title_norm) or (t_no_the and t_no_the in result_title_norm):
            artist_score = max(artist_score, 0.75)

    if artist_score < 0.5:
        return 0.0

    if title_score < 0.5:
        return 0.0

    album_score = 1.0
    expected_album = track.get('album', '')
    result_album = (result.get('album') or {}).get('name', '')
    if expected_album and result_album:
        album_score = word_ratio(clean(expected_album), clean(result_album))

    album_weight = 0.3 if title_score >= 0.9 else 0.2
    return title_score * 0.4 + artist_score * 0.3 + album_score * album_weight
