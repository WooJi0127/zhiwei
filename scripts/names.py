# -*- coding: utf-8 -*-
"""
名称规范化与中文化

用户要求：优先中文 > 英文 > 韩文。
K-pop 实际情况：四代以后的团体绝大多数没有官方中文名，英文名本身就是官方名。
因此策略是：
  1) 少数确有通用中文名的（防弹少年团、东方神起、少女时代…）→ 显示中文 + 英文
  2) 其余 → 英文名（本就是官方名，不算降级）
  3) 韩文名 → 尽量归一到英文，避免界面上出现韩文
"""
import re
import unicodedata

# ---------------------------------------------------------- 中文名映射
# 只收录"确有通用中文名 / 通用译名"的，宁缺毋滥。
# 注意：多数四代以后的团体英文名本身就是官方名，直译（如 Stray Kids -> 流浪儿童）
# 反而会造成误解，因此一律不填，走英文显示。
ARTIST_ZH_OFFICIAL = {
    # 团体（官方中文名）
    "BTS": "防弹少年团",
    "TVXQ!": "东方神起",
    "Girls' Generation": "少女时代",
    "WayV": "威神V",
    # 个人歌手（通用中文译名）
    "IU": "李知恩",
    "BoA": "宝儿",
    "Taeyeon": "太妍",
    "Sunmi": "宣美",
    "Chungha": "请夏",
    "Hwasa": "华莎",
    "Hyuna": "泫雅",
    "Kang Daniel": "姜丹尼尔",
    "Baekhyun": "伯贤",
    "D.O.": "都敬秀",
    "Baek Yerin": "白艺潾",
    "Yerin Baek": "白艺潾",
    "Lee Hi": "李遐怡",
    "Kim Sejeong": "金世正",
    "Jung Seung Hwan": "郑承焕",
    "Sunwoo Junga": "鲜于贞娥",
    "Younha": "尹荷",
    "Ailee": "Ailee",
    # 团体成员（通用译名，粉丝圈通行）
    "Jimin": "智旻",
    "Jungkook": "柾国",
    "Nayeon": "娜琏",
    "Jeongyeon": "定延",
    "Momo": "桃",
    "Sana": "纱奈",
    "Jihyo": "志效",
    "Mina": "美娜",
    "Dahyun": "多贤",
    "Chaeyoung": "彩瑛",
    "Tzuyu": "子瑜",
    "Jennie": "珍妮",
    "Lisa": "丽莎",
    "Rosé": "罗婕",
    "Jisoo": "智秀",
    "Karina": "卡琳娜",
    "Giselle": "吉赛尔",
    "Winter": "温特",
    "Ningning": "宁宁",
    # 中文圈有官方中文名的成员（NCT / WayV 等以中文活动的组合）
    "Taeyong": "李泰容",
    "Doyoung": "金道英",
    "Jaehyun": "郑在玹",
    "Mark": "李马克",
    "Haechan": "李东赫",
    "Jeno": "李帝努",
    "Jaemin": "罗渽民",
    "Renjun": "黄仁俊",
    "Chenle": "钟辰乐",
    "Jisung": "朴志晟",
    "Kun": "钱锟",
    "Xiaojun": "肖俊",
    "Hendery": "黄冠亨",
    "Yangyang": "刘扬扬",
    "Winwin": "董思成",
    # 其他常用译名的个人歌手
    "Hyolyn": "孝琳",
    "Taemin": "泰民",
    "Minho": "珉豪",
    "Onew": "温流",
    "Kim Jaehwan": "金在奂",
    "Hwang Min Hyun": "黄旼炫",
    "Kangta": "安七炫",
    "Baekho": "白虎",
    "Suho": "金俊勉",
    "Chen": "金钟大",
    "Xiumin": "金珉锡",
    "Chanyeol": "朴灿烈",
    "Sehun": "吴世勋",
    "Kai": "金钟仁",
    "Sung Si Kyung": "成始璄",
    "Lee Seung Gi": "李升基",
    "Kyuhyun": "圭贤",
    "Ryeowook": "厉旭",
    "Yesung": "艺声",
    "Eunhyuk": "银赫",
    "Donghae": "东海",
    "Siwon": "崔始源",
    "Leeteuk": "利特",
    "Heechul": "希澈",
    "Shindong": "神童",
}

ARTIST_ZH = dict(ARTIST_ZH_OFFICIAL)   # 仅保留可靠中文名，见上方 OFFICIAL 表


# ---------------------------------------------------------- 母公司归并
# 把子公司归到母公司，避免筛选列表里一堆看不出关系的厂牌
AGENCY_PARENT = {
    # HYBE 系
    "HYBE": "HYBE", "BIGHIT MUSIC": "HYBE", "BigHit Music": "HYBE",
    "BELIFT LAB": "HYBE", "BELIFT": "HYBE",
    "PLEDIS Entertainment": "HYBE", "PLEDIS": "HYBE",
    "ADOR": "HYBE", "SOURCE MUSIC": "HYBE", "Source Music": "HYBE",
    "KOZ Entertainment": "HYBE", "KOZ": "HYBE",
    "HYBE LABELS JAPAN": "HYBE", "YX LABELS": "HYBE", "NAECO": "HYBE",
    # SM 系
    "SM Entertainment": "SM", "S.M. Entertainment": "SM",
    "SM TOWN": "SM", "Label SJ": "SM", "Mystic Story": "SM",
    # JYP 系
    "JYP Entertainment": "JYP", "SQU4D": "JYP", "Studio J": "JYP",
    # YG 系
    "YG Entertainment": "YG", "YG PLUS": "YG",
    "THE BLACK LABEL": "YG", "The Black Label": "YG",
    # Kakao 系
    "Kakao Entertainment": "Kakao Entertainment", "Kakao M": "Kakao Entertainment",
    "Starship Entertainment": "Kakao Entertainment",
    "IST Entertainment": "Kakao Entertainment",
    "EDAM Entertainment": "Kakao Entertainment",
    "High Up Entertainment": "Kakao Entertainment", "HIGHUP": "Kakao Entertainment",
    "Antenna": "Kakao Entertainment", "Bluedot Entertainment": "Kakao Entertainment",
    "AER Music": "Kakao Entertainment", "FLEX M": "Kakao Entertainment",
    "WM Entertainment": "Kakao Entertainment", "Highline": "Kakao Entertainment",
    # CJ ENM 系
    "WAKEONE": "CJ ENM", "LAPONE Entertainment": "CJ ENM",
    "Swing Entertainment": "CJ ENM", "Amoeba Culture": "CJ ENM",
    "OFF THE RECORD": "CJ ENM",
    # 其他独立厂牌
    "CUBE Entertainment": "CUBE", "FNC Entertainment": "FNC",
    "KQ Entertainment": "KQ", "RBW": "RBW",
    "Woollim Entertainment": "Woollim", "Jellyfish Entertainment": "Jellyfish",
    "Fantagio": "Fantagio", "Star Empire Entertainment": "Star Empire",
    "MBK Entertainment": "MBK", "Modhaus": "Modhaus",
    "8D Entertainment": "8D Entertainment", "P Nation": "P Nation",
    "AOMG": "AOMG", "H1GHR MUSIC": "H1GHR MUSIC",
    "Konnect Entertainment": "Konnect", "BPM Entertainment": "BPM",
    "Grandline Group": "Grandline", "Big Ocean ENM": "Big Ocean ENM",
    "Yuehua Entertainment": "Yuehua", "Genie Music": "Genie Music",
    "Sony Music": "Sony Music", "Universal Music": "Universal Music",
    "Warner Music": "Warner Music",
}

# 模糊匹配用（长名在前，避免短名误伤）
_AGENCY_KEYS = sorted(AGENCY_PARENT.keys(), key=len, reverse=True)


def parent_agency(a):
    """'KQ Entertainment (HYBE)' -> 'KQ'；未收录的原样返回"""
    if not a:
        return a
    s = re.sub(r"\s*\([^)]*\)\s*", "", a).strip()
    if s in AGENCY_PARENT:
        return AGENCY_PARENT[s]
    if a in AGENCY_PARENT:
        return AGENCY_PARENT[a]
    low = s.lower()
    for k in _AGENCY_KEYS:
        if k.lower() in low:
            return AGENCY_PARENT[k]
    return s or a


# ------------------------------------------- 已知艺人分类（兜底，优先级最低）
# kpopcal + kpopping 名录覆盖了大部分，剩下这些是脚本抓不到但我能确定的
KNOWN_GROUPS = {
    "FTISLAND", "JUSTB", "LIGHTSUM", "EVNNE", "n.SSign", "ME:I", "ONE OR EIGHT",
    "H//PE Princess", "LUNEDI", "MODYSSEY", "MW:MEU", "NAZE", "IRISÉ",
    "Heart Of Woman", "FLARE U", "Rescene", "NOWZ", "UAU", "SAY MY NAME",
    "izna", "KiiiKiii", "Hearts2Hearts", "KickFlip", "MEOVV", "ALLDAY PROJECT",
    "HITGS", "AHOF", "KIIRAS", "IDID", "CLOSE YOUR EYES", "XLOV", "ablume",
    "ifeye", "Baby DONT Cry", "Secret Number", "PURPLE KISS", "Billlie", "Weeekly",
    "Rocket Punch", "ICHILLIN'", "TRI.BE", "PIXY", "EPEX", "TAN", "OMEGA X",
    "Xdinary Heroes", "ONEUS", "VERIVERY", "DKB", "E'LAST", "TO1", "Ciipher",
    "BAE173", "TRENDZ", "Ghost9", "Weki Meki", "cignature", "WOOAH", "Cherry Bullet",
    "LUNARSOLAR", "ARIAZ", "ANZ", "REDSQUARE", "BVNDIT", "Pink Fantasy", "Saturday",
    "Bling Bling", "Bvndit", "Nature", "Girls on Top", "Bolbbalgan4", "10cm",
    "Se So Neon", "JANNABI", "DAY6", "THE ROSE", "Lucy", "Hoppypolis", "Kiha & The Faces",
}
KNOWN_SOLO = {
    "Onew", "Jay Park", "Hyolyn", "Minzy", "Kim Jaehwan", "Park Bo Gum",
    "Mark Tuan", "Max Changmin", "Lee Chae Yeon", "Moon Sujin", "eaJ", "pH-1",
    "Loco", "Jay B", "Jooyoung", "Jaehyuk", "Hwang Min Hyun", "Hendery", "HaSeul",
    "Hyojung", "Nana", "Min Jiwoon", "Hangyul", "Kim Ji Woong", "Lee Dongyeol",
    "Bailey", "Yuju", "Jung Yong Hwa", "Lee Hong Ki", "Crucial Star", "Sik-K",
    "Crush", "DEAN", "Zion.T", "Heize", "Baek Ye Rin", "Lee Hi", "Sunwoo Junga",
    "Jung Seung Hwan", "Kassy", "Kwon Jin Ah", "Cheeze", "Jaurim", "Zico", "Paul Kim",
    "Jungkook", "Ten", "Kun", "Xiaojun", "Yangyang", "Winwin", "Wonho", "Kihyun",
    "Shownu", "Minhyuk", "Hyungwon", "Joohoney", "IM", "Sungjae", "Doyoung",
    "Taeyong", "Haechan", "Jeno", "Jaemin", "Renjun", "Chenle", "Jisung",
    "Yooa", "Seulgi", "Wendy", "Joy", "Yeri", "Irene", "Solar", "Moonbyul",
    "Wheein", "Hwasa", "Sohee", "Bora", "Sua", "Soyeon", "Miyeon", "Minnie",
    "Yuqi", "Shuhua", "Soyeon", "Gaeul", "Liz", "Leeseo", "Yujin", "Rei",
    "Wonyoung", "Giselle", "Ningning", "Winter", "Karina", "Nayeon", "Jihyo",
    "Momo", "Sana", "Mina", "Dahyun", "Chaeyoung", "Tzuyu", "Jeongyeon",
    "Hongjoong", "Seonghwa", "Yunho", "Yeosang", "San", "Mingi", "Wooyoung",
    "Jongho", "Cha Eun Woo", "Moonbin", "Sanha", "Jinjin", "MJ", "Rocky",
    "Yoon Sanha", "Bang Chan", "Lee Know", "Changbin", "Hyunjin", "Han",
    "Felix", "Seungmin", "I.N", "Choi San", "Kang Seungyoon", "Mino",
    "Jinusean", "Bobby", "B.I", "June", "DK", "Seungkwan", "Hoshi", "Wonwoo",
    "Woozi", "The8", "Mingyu", "DK", "Vernon", "Dino", "S.Coups", "Jeonghan",
    "Joshua", "Jun", "Hwang Min-hyun", "Baekho", "Minhyun", "JR", "Aron", "Ren",
    "Leedo", "Keonhee", "Hwanwoong", "Seoho", "Xion", "Ravn", "Dongju", "Yeonjun",
    "Soobin", "Beomgyu", "Taehyun", "Huening Kai", "Haechan", "Jeno", "Jaemin",
    "Jisung", "Renjun", "Chenle", "Jeno", "Mark", "Taeyong", "Doyoung", "Jaehyun",
}


def kind_of(name):
    """兜底判断艺人类型。返回 group / solo / None（不确定）。"""
    if not name:
        return None
    if name in KNOWN_GROUPS:
        return "group"
    if name in KNOWN_SOLO:
        return "solo"
    return None


# ---------------------------------------------------------- 性别（男团/女团/混团等）
def norm_gkey(s):
    """
    性别表比对用的 key：去重音、去符号、小写、去掉 slug 尾部的同名数字。
    例：'ROSÉ' -> 'rose'，'Yena2' -> 'yena'，'Tomorrow-X-Together2' -> 'tomorrowxtogether'
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return re.sub(r"\d+$", "", s)


# 手工补录：kpopping 的四个名录页抓不到的部分。
# 只写有把握的；不确定的宁可留空（会落到「团体 / Solo」里，不会误分到男女）。
# 值：F=女  M=男  X=混声
GENDER_OVERRIDE = {
    # --- 团体 ---
    "XG": "F",                    # 女团（日本活动为主的 K-pop 女团）
    "n.SSign": "M",
    "WAYF BOYS": "M",
    # --- 男歌手 ---
    "Bang Yedam": "M",            # TREASURE
    "Donghae": "M",               # SUPER JUNIOR
    "Eric Nam": "M",
    "Eunsang": "M",               # X1
    "Hangyul": "M",               # X1
    "Hwang Min Hyun": "M",        # NU'EST
    "Jaehyuk": "M",               # TREASURE
    "Jooyoung": "M",
    "Kim Jaehwan": "M",
    "Kim Ji Woong": "M",          # ZEROBASEONE
    "Lee Dongyeol": "M",
    "Loco": "M",                  # 说唱歌手
    "Mark Tuan": "M",             # GOT7
    "Max Changmin": "M",          # 东方神起
    "PARK BYEONG HOON": "M",
    "Park Bo Gum": "M",
    "Seo In Guk": "M",
    "Sik-k": "M",                 # 说唱歌手
    "Siwan": "M",                 # ZE:A
    "Woohyun": "M",               # INFINITE
    "Yesung": "M",                # SUPER JUNIOR
    "Zion. T": "M",
    "eaJ": "M",                   # DAY6
    "pH-1": "M",                  # 说唱歌手
    # --- 女歌手 ---
    "Hyojung": "F",               # OH MY GIRL
    "Hyolyn": "F",                # SISTAR
    "Mei Qi": "F",
    "Minzy": "F",                 # 2NE1
    "Moon Sujin": "F",
    "Ryu Sujeong": "F",           # Lovelyz
    "Serri": "F",                 # Dal Shabet
    "Shannon Bae": "F",
    "Victoria": "F",              # f(x)
    "Youha": "F",
}
_GENDER_KEYS = {norm_gkey(k): v for k, v in GENDER_OVERRIDE.items()}


def gender_override(name):
    return _GENDER_KEYS.get(norm_gkey(name))


# ------------------------------------------------- 韩文名 -> 英文（兜底归一）
# 主要用于 Apple Music 韩国区偶尔返回韩文艺人名的情况
ARTIST_KO = {
    "트리플에스": "tripleS",
    "방탄소년단": "BTS",
    "동방신기": "TVXQ!",
    "소녀시대": "Girls' Generation",
    "슈퍼주니어": "SUPER JUNIOR",
    "빅뱅": "BIGBANG",
    "블랙핑크": "BLACKPINK",
    "트와이스": "TWICE",
    "레드벨벳": "Red Velvet",
    "엑소": "EXO",
    "세븐틴": "SEVENTEEN",
    "스트레이 키즈": "Stray Kids",
    "있지": "ITZY",
    "아이브": "IVE",
    "에스파": "aespa",
    "뉴진스": "NewJeans",
    "르세라핌": "LE SSERAFIM",
    "엔믹스": "NMIXX",
    "엔하이픈": "ENHYPEN",
    "투모로우바이투게더": "TOMORROW X TOGETHER",
    "태연": "Taeyeon",
    "아이유": "IU",
    "선미": "Sunmi",
    "청하": "Chungha",
    "화사": "Hwasa",
    "현아": "Hyuna",
    "도경수": "D.O.",
    "에릭남": "Eric Nam",
    "백현": "Baekhyun",
    "지효": "Jihyo",
    "나연": "Nayeon",
    "정연": "Jeongyeon",
    "모모": "Momo",
    "사나": "Sana",
    "미나": "Mina",
    "다현": "Dahyun",
    "채영": "Chaeyoung",
    "쯔위": "Tzuyu",
    "카리나": "Karina",
    "윈터": "Winter",
    "지젤": "Giselle",
    "닝닝": "Ningning",
    "제니": "Jennie",
    "리사": "Lisa",
    "로제": "Rosé",
    "지수": "Jisoo",
}

# 补充：Apple Music 会用韩文书写艺人名，这里补一批常见的
ARTIST_KO.update({
    "쇼뮤지컬 드림하이 댄스패밀리": "Dream High Dance Family",
    "니쥬": "NiziU",
    "하슬": "HaSeul",
    "디디": "DΔDΔ",
    "박병훈": "Park Byeonghoon",
    "82메이저": "82MAJOR",
    "레이": "LAY",
    "홍중": "Hongjoong",
    "홍진경": "Hong Jinkyung",
    "박재범": "Jay Park",
    "정선혜": "Jung Sunhye",
    "황정민": "Hwang Jungmin",
    "데프콘": "Defconn",
    "정형돈": "Jung Hyungdon",
    "조세호": "Jo Seho",
    "기안84": "Kian84",
    "안성재": "Ahn Sungjae",
    "태양": "TAEYANG",
    "정해인": "Jung Haein",
    "황광희": "Hwang Kwanghee",
    "임시완": "Im Siwan",
    "이수혁": "Lee Soohyuk",
    "대성": "DAESUNG",
    "코드 쿤스트": "CODE KUNST",
    "김고은": "Kim Goeun",
    "데이식스": "DAY6",
    "부석순": "BSS",
    "엔하이픈": "ENHYPEN",
    "나연": "Nayeon",
    "로제": "Rosé",
    "지드래곤": "G-DRAGON",
    "권지용": "G-DRAGON",
    "이지은": "IU",
    "김태형": "V",
    "전정국": "Jungkook",
    "박지민": "Jimin",
    "민윤기": "SUGA",
    "정호석": "J-Hope",
    "김남준": "RM",
    "김석진": "Jin",
    "이태민": "Taemin",
    "김기범": "Key",
    "최민호": "Minho",
    "이진기": "Onew",
    "김종현": "Jonghyun",
    "변백현": "Baekhyun",
    "박찬열": "Chanyeol",
    "오세훈": "Sehun",
    "김종인": "KAI",
    "김준면": "SUHO",
    "장이씽": "Lay",
    "김민석": "XIUMIN",
    "도경수": "D.O.",
    "김종대": "Chen",
})

RE_HANGUL = re.compile(r"[\uac00-\ud7a3]")
RE_SPLIT = re.compile(r"\s*(?:,|&|、|feat\.?|with)\s*", re.I)


def has_hangul(s):
    return bool(s and RE_HANGUL.search(s))


def clean_mixed(s):
    """
    清理组合艺人名里的韩文片段。
    'Alex Warren & 로제' -> 'Alex Warren'；全韩文且无映射 -> None
    """
    if not s:
        return s
    # 先去掉含韩文的括号补充，如 'NOWZ (나우즈)' -> 'NOWZ'
    s = re.sub(r"\s*[\(（][^)）]*[\uac00-\ud7a3][^)）]*[\)）]\s*", " ", s).strip()
    if not s:
        return None
    if not has_hangul(s):
        return s
    if s.strip() in ARTIST_KO:
        return ARTIST_KO[s.strip()]
    parts = [p.strip() for p in RE_SPLIT.split(s) if p.strip()]
    keep = []
    for p in parts:
        if has_hangul(p):
            if p in ARTIST_KO:
                keep.append(ARTIST_KO[p])
            continue
        keep.append(p)
    if keep:
        return " & ".join(keep[:3])
    return None


def reconcile_artist(nm, known):
    """
    把合作曲的组合艺人名归到真正的主艺人。
    'Alok, 나연 & TWICE' + known={TWICE,...} -> 'TWICE'
    'Alex Warren & 로제'  + known={Rosé,...}  -> 'Rosé'
    匹配不到再退回 clean_mixed。
    """
    if not nm:
        return nm
    if nm in known:
        return nm
    parts = [p.strip() for p in RE_SPLIT.split(nm) if p.strip()]
    hits = [p for p in parts if p in known]
    if hits:
        return max(hits, key=len)
    return clean_mixed(nm) or nm


def norm_artist(name):
    """把艺人名归一为英文（去韩文）。找不到映射就原样返回。"""
    if not name:
        return name
    n = name.strip()
    if n in ARTIST_KO:
        return ARTIST_KO[n]
    return n


def zh_of(name):
    """取中文名，没有则 None。"""
    if not name:
        return None
    return ARTIST_ZH.get(name.strip())


def display(name):
    """
    返回展示用名称：
      (主名称, 副名称)
      有中文名 -> (中文, 英文)；否则 -> (英文, None)
    """
    n = norm_artist(name)
    z = zh_of(n)
    if z and z != n:
        return z, n
    return n, None
