"""生日区的可选常用中文名；未核验的人名留空，不自动音译。

不能复用 names.ARTIST_ZH：全局英文名键会把不同团体的同名成员混淆。
这里仅按明确登记的「团体 + 艺名」查找；有生日时还必须与登记生日一致。
来源支持的是中文常用写法，不声称所有名字都是官方汉字正名；繁体按站点
语言写成简体。生日/分队身份取自现有 catalog/members.jsonl，仅用作身份
校验，不覆盖原始 n、b，也不凭生日反向猜名字。别名和分队逐人明确登记。
个人艺名作为 g 的条目只是兼容目录里已有的同一人记录，不扩抓 solo 生日。

新增条目时先核验来源，再补数据和测试。禁止子串、音译、去标点或全局
人名兜底。来源最近核验日期：2026-11-01。
"""
from dataclasses import dataclass
import unicodedata


SOURCES = {
    "bts_koreana": {
        "title": "韩国国际交流财团 Koreana：BTS 七位成员的姓名及生日",
        "url": "https://www.koreana.or.kr/koreana/na/ntt/selectNttInfo.do?bbsId=1114&langTy=KOR&mi=1544&nttSn=52103",
    },
    "twice_zaobao": {
        "title": "联合早报：TWICE 新加坡演出报道，九人中英文姓名对应",
        "url": "https://www.zaobao.com.sg/zvideos/entertainment/story20190715-972457",
    },
    "blackpink_elle": {
        "title": "ELLE Taiwan：BLACKPINK 巴黎时装周，Jisoo、Jennie、Rosé 中英文名",
        "url": "https://www.elle.com/tw/fashion/celeb-style/g41421963/blackpink-pfw-style/",
    },
    "aespa_karina": {
        "title": "ELLE HK：Karina 柳智敏人物介绍",
        "url": "https://www.elle.com.hk/fashion/kpop-sm-girl-group-aespa-leader-karina-prada-style-file-update",
    },
    "aespa_winter": {
        "title": "ELLE HK：aespa 成员介绍，Winter 金玟庭",
        "url": "https://www.elle.com.hk/fashion/aespa-style-file",
    },
    "aespa_giselle": {
        "title": "ELLE HK：Giselle 内永枝利人物介绍",
        "url": "https://www.elle.com.hk/fashion/aespa-giselle-style-profile",
    },
    "aespa_ningning": {
        "title": "ELLE HK：Ningning 宁艺卓人物介绍",
        "url": "https://www.elle.com.hk/fashion/aespa-ningning-style-file",
    },
    "ive_zaobao": {
        "title": "联合早报：IVE 六人中英文姓名，张元英亦写作张员瑛",
        "url": "https://www.zaobao.com.sg/entertainment/story20260511-9025136",
    },
    "seventeen_vogue": {
        "title": "Vogue Taiwan：SEVENTEEN 成员介绍及中文常用名",
        "url": "https://www.vogue.com.tw/article/all-about-seventeen",
    },
    "hoshi_vogue": {
        "title": "Vogue HK：SEVENTEEN Hoshi 权顺荣人物介绍",
        "url": "https://www.voguehk.com/zh/article/celebrity/seventeen-hoshi-diesel/",
    },
    "joshua_elle": {
        "title": "ELLE HK：SEVENTEEN Joshua 洪知秀品牌专访",
        "url": "https://www.elle.com.hk/fashion/jlc-joshua",
    },
    "exo_cbx": {
        "title": "联合早报：EXO-CBX 伯贤、金珉锡、金钟大姓名对应",
        "url": "https://www.zaobao.com.sg/entertainment/story20230607-1402099",
    },
    "exo_concert": {
        "title": "联合早报：EXO 新加坡演出成员中英文名",
        "url": "https://www.zaobao.com.sg/zvideos/entertainment/story20180307-840521",
    },
    "exo_lay_do": {
        "title": "联合早报：EXO 的 LAY 张艺兴及 D.O. 都敬秀",
        "url": "https://www.zaobao.com.sg/entertainment/story20220408-1260674",
    },
    "nmixx_zaobao": {
        "title": "联合早报：NMIXX 六人中英文姓名（2026 年演出报道）",
        "url": "https://www.zaobao.com.sg/entertainment/story20260622-9239623",
    },
    "itzy_zaobao": {
        "title": "联合早报专访：ITZY 五人中英文姓名",
        "url": "https://www.zaobao.com.sg/zvideos/entertainment/story20201026-1095868",
    },
    "straykids_zaobao": {
        "title": "联合早报：Stray Kids 方灿、彰彬、铉辰、昇玟中英文对应",
        "url": "https://www.zaobao.com.sg/entertainment/story20230209-1361326",
    },
    "lesserafim_vogue": {
        "title": "Vogue Taiwan 亲访：LE SSERAFIM 四名成员中英文名",
        "url": "https://www.vogue.com.tw/video/watch/le-sserafimhui-da-wang-you-re-sou-wen-da",
    },
    "lesserafim_zaobao": {
        "title": "联合早报：LE SSERAFIM 五位成员，含宫胁咲良",
        "url": "https://www.zaobao.com.sg/entertainment/story20250819-7376391",
    },
    "bts_individual_names": {
        "title": "BIGHIT 官方 BTS 简介：j-hope 与 Jung Kook 的成员身份和艺名拼写",
        "url": "https://bts.ibighit.com/eng/profile/",
    },
    "nayeon_solo": {
        "title": "KBS WORLD：TWICE Nayeon 以本人艺名发表个人专辑",
        "url": "https://world.kbs.co.kr/service/contents_view.htm?board_seq=423059&lang=e",
    },
    "blackpink_solos": {
        "title": "KBS WORLD 中文：BLACKPINK 成员 Jennie、Jisoo、Rosé 的个人作品",
        "url": "https://world.kbs.co.kr/service/contents_view.htm?board_seq=437429&lang=c&menu_cate=enternews",
    },
    "sm_project_groups": {
        "title": "SM 官方可持续发展报告：GOT the beat 的 Karina/Winter，SuperM 的 Baekhyun/Kai",
        "url": "https://cdn2.smentertainment.com/wp-content/uploads/2024/02/2021_SM_ENTERTAINMENT_sustainability_report_EN.pdf",
    },
    "izone_ive": {
        "title": "Vogue Taiwan：安俞真、张员瑛自 IZ*ONE 到 IVE 的经历",
        "url": "https://www.vogue.com.tw/article/ive-an-yujin-jang-wonyoung-an-young",
    },
    "izone_lesserafim": {
        "title": "Vogue Taiwan：宫胁咲良、金采源曾以 IZ*ONE 成员身份活动",
        "url": "https://www.vogue.com.tw/article/all-about-le-sserafim",
    },
    "seventeen_units": {
        "title": "PLEDIS 官方 SEVENTEEN 简介：三支分队逐人成员名单",
        "url": "https://www.pledis.co.kr/artist/detail/seventeen/profile/",
    },
    "seventeen_mixed_units": {
        "title": "Weverse Magazine：SVT Leaders、BSS、JxW、HxW、CxM、DxS 的成员组成",
        "url": "https://magazine.weverse.io/article/view/1744?lang=en",
    },
    "seventeen_jxj": {
        "title": "Weverse 官方 JEONGHAN X JOSHUA 演出及 SEVENTEEN 会员说明",
        "url": "https://concerts.weverse.io/events/jxj_dreaming",
    },
    "seventeen_v8": {
        "title": "PLEDIS 官方公告：V8 由 THE 8 与 VERNON 组成",
        "url": "https://weverse.io/seventeen/notice/36512",
    },
    "seventeen_individuals": {
        "title": "SEVENTEEN 官方 Weverse：Hoshi、Joshua、Jun 个人发行与幕后内容",
        "url": "https://weverse.io/SEVENTEEN/media",
    },
    "exo_individuals": {
        "title": "KBS WORLD EXO 简介：成员艺名及各自个人活动",
        "url": "https://world.kbs.co.kr/service/contents_view.htm?board_seq=352301&menu_cate=artist",
    },
    "sm_performance": {
        "title": "Bugs 正版音源 SM 专辑介绍：SM The Performance 包含 EXO-K Kai 和 EXO-M Lay",
        "url": "https://music.bugs.co.kr/album/353266",
    },
    "kai_younique": {
        "title": "KBS WORLD KAI 简介：EXO、EXO-K、Younique Unit、SuperM 的成员身份",
        "url": "https://world.kbs.co.kr/service/contents_view.htm?board_code=music_artist&board_seq=395859&id=&lang=e&menu_cate=artist&page=9",
    },
    "chaeryeong_solo": {
        "title": "JYP ITZY 官方公告：CHAERYEONG 的 Mine 个人舞台",
        "url": "https://itzy.jype.com/Mobile/NoticeView?AnSeq=856&NoticeNumber=885",
    },
}


@dataclass(frozen=True)
class MemberName:
    groups: tuple[str, ...]
    name: str
    birth: str
    zh: str
    source_ids: tuple[str, ...]


# 每个分队都逐人列出；例如 Kai 不属于 EXO-CBX，不能把 EXO-* 整体归并。
MEMBER_NAMES = (
    MemberName(("BTS", "j-hope"), "J-hope", "1994-02-18", "郑号锡", ("bts_koreana", "bts_individual_names")),
    MemberName(("BTS",), "Jimin", "1995-10-13", "朴智旻", ("bts_koreana",)),
    MemberName(("BTS",), "Jin", "1992-12-04", "金硕珍", ("bts_koreana",)),
    MemberName(("BTS", "Jung Kook"), "Jungkook", "1997-09-01", "田柾国", ("bts_koreana", "bts_individual_names")),
    MemberName(("BTS",), "RM", "1994-09-12", "金南俊", ("bts_koreana",)),
    MemberName(("BTS",), "Suga", "1993-03-09", "闵玧其", ("bts_koreana",)),
    MemberName(("BTS",), "V", "1995-12-30", "金泰亨", ("bts_koreana",)),
    MemberName(("TWICE",), "Chaeyoung", "1999-04-23", "孙彩瑛", ("twice_zaobao",)),
    MemberName(("TWICE",), "Dahyun", "1998-05-28", "金多贤", ("twice_zaobao",)),
    MemberName(("TWICE",), "Jeongyeon", "1996-11-01", "俞定延", ("twice_zaobao",)),
    MemberName(("TWICE",), "Jihyo", "1997-02-01", "朴志效", ("twice_zaobao",)),
    MemberName(("TWICE", "MISAMO"), "Mina", "1997-03-24", "名井南", ("twice_zaobao",)),
    MemberName(("TWICE", "MISAMO"), "Momo", "1996-11-09", "平井桃", ("twice_zaobao",)),
    MemberName(("TWICE", "Nayeon"), "Nayeon", "1995-09-22", "林娜琏", ("twice_zaobao", "nayeon_solo")),
    MemberName(("TWICE", "MISAMO"), "Sana", "1996-12-29", "凑崎纱夏", ("twice_zaobao",)),
    MemberName(("TWICE",), "Tzuyu", "1999-06-14", "周子瑜", ("twice_zaobao",)),
    MemberName(("BLACKPINK", "Jennie"), "Jennie", "1996-01-16", "金珍妮", ("blackpink_elle", "blackpink_solos")),
    MemberName(("BLACKPINK", "Jisoo"), "Jisoo", "1995-01-03", "金智秀", ("blackpink_elle", "blackpink_solos")),
    MemberName(("BLACKPINK", "Rosé"), "Rosé", "1997-02-11", "朴彩英", ("blackpink_elle", "blackpink_solos")),
    MemberName(("aespa", "GOT the beat"), "Karina", "2000-04-11", "柳智敏", ("aespa_karina", "sm_project_groups")),
    MemberName(("aespa", "GOT the beat"), "Winter", "2001-01-01", "金玟庭", ("aespa_winter", "sm_project_groups")),
    MemberName(("aespa",), "Giselle", "2000-10-30", "内永枝利", ("aespa_giselle",)),
    MemberName(("aespa",), "Ningning", "2002-10-23", "宁艺卓", ("aespa_ningning",)),
    MemberName(("IVE", "IZ*ONE"), "An Yujin", "2003-09-01", "安俞真", ("ive_zaobao", "izone_ive")),
    MemberName(("IVE",), "Gaeul", "2002-09-24", "金秋天", ("ive_zaobao",)),
    MemberName(("IVE", "IZ*ONE"), "Jang Wonyoung", "2004-08-31", "张元英", ("ive_zaobao", "izone_ive")),
    MemberName(("IVE",), "Leeseo", "2007-02-21", "李贤瑞", ("ive_zaobao",)),
    MemberName(("IVE",), "Liz", "2004-11-21", "金志垣", ("ive_zaobao",)),
    MemberName(("IVE",), "Rei", "2004-02-03", "直井怜", ("ive_zaobao",)),
    MemberName(("SEVENTEEN", "BSS", "Hoshi", "Hoshi X Woozi", "SVT Leaders", "SVT PERFORMANCE Team"), "Hoshi", "1996-06-15", "权顺荣", ("hoshi_vogue", "seventeen_units", "seventeen_mixed_units", "seventeen_individuals")),
    MemberName(("SEVENTEEN", "Jeonghan X Joshua", "Jeonghan X Wonwoo", "SVT VOCAL Team"), "Jeonghan", "1995-10-04", "净汉", ("seventeen_vogue", "seventeen_units", "seventeen_mixed_units", "seventeen_jxj")),
    MemberName(("SEVENTEEN", "Jeonghan X Joshua", "Joshua", "SVT VOCAL Team"), "Joshua", "1995-12-30", "洪知秀", ("joshua_elle", "seventeen_units", "seventeen_jxj", "seventeen_individuals")),
    MemberName(("SEVENTEEN", "Jun", "SVT PERFORMANCE Team"), "Jun", "1996-06-10", "文俊辉", ("seventeen_vogue", "seventeen_units", "seventeen_individuals")),
    MemberName(("SEVENTEEN", "S.Coups X Mingyu", "SVT HIPHOP Team"), "Mingyu", "1997-04-06", "珉奎", ("seventeen_vogue", "seventeen_units", "seventeen_mixed_units")),
    MemberName(("SEVENTEEN", "BSS", "DK X Seungkwan", "SVT VOCAL Team"), "Seungkwan", "1998-01-16", "胜宽", ("seventeen_vogue", "seventeen_units", "seventeen_mixed_units")),
    MemberName(("SEVENTEEN", "SVT PERFORMANCE Team", "V8"), "The8", "1997-11-07", "徐明浩", ("seventeen_vogue", "seventeen_units", "seventeen_v8")),
    MemberName(("SEVENTEEN", "Jeonghan X Wonwoo", "SVT HIPHOP Team"), "Wonwoo", "1996-07-17", "圆佑", ("seventeen_vogue", "seventeen_units", "seventeen_mixed_units")),
    MemberName(("EXO", "EXO-K", "EXO-CBX", "Baekhyun", "SuperM"), "Baekhyun", "1992-05-06", "伯贤", ("exo_cbx", "sm_project_groups", "exo_individuals")),
    MemberName(("EXO", "EXO-K", "EXO-SC", "Chanyeol"), "Chanyeol", "1992-11-27", "朴灿烈", ("exo_concert", "exo_individuals")),
    MemberName(("EXO", "EXO-M", "EXO-CBX"), "Chen", "1992-09-21", "金钟大", ("exo_cbx",)),
    MemberName(("EXO", "EXO-K", "D.O."), "D.O.", "1993-01-12", "都敬秀", ("exo_lay_do", "exo_individuals")),
    MemberName(("EXO", "EXO-K", "SM The Performance", "SuperM", "Younique Unit"), "Kai", "1994-01-14", "金钟仁", ("exo_concert", "sm_project_groups", "sm_performance", "kai_younique")),
    MemberName(("EXO", "EXO-M", "Lay", "SM The Performance"), "Lay", "1991-10-07", "张艺兴", ("exo_lay_do", "exo_individuals", "sm_performance")),
    MemberName(("EXO", "EXO-K", "EXO-SC"), "Sehun", "1994-04-12", "吴世勋", ("exo_concert",)),
    MemberName(("EXO", "EXO-K"), "Suho", "1991-05-22", "金俊勉", ("exo_concert",)),
    MemberName(("EXO", "EXO-M", "EXO-CBX"), "Xiumin", "1990-03-26", "金珉锡", ("exo_cbx",)),
    MemberName(("NMIXX",), "Bae", "2004-12-28", "裴真率", ("nmixx_zaobao",)),
    MemberName(("NMIXX",), "Haewon", "2003-02-25", "吴海嫄", ("nmixx_zaobao",)),
    MemberName(("NMIXX",), "Jiwoo", "2005-04-13", "金智友", ("nmixx_zaobao",)),
    MemberName(("NMIXX",), "Kyujin", "2006-05-26", "张圭珍", ("nmixx_zaobao",)),
    MemberName(("NMIXX",), "Lily", "2002-10-17", "朴珍", ("nmixx_zaobao",)),
    MemberName(("NMIXX",), "Sullyoon", "2004-01-26", "薛仑娥", ("nmixx_zaobao",)),
    MemberName(("ITZY", "Chaeryeong"), "Chaeryeong", "2001-06-05", "李彩领", ("itzy_zaobao", "chaeryeong_solo")),
    MemberName(("ITZY",), "Lia", "2000-07-21", "崔智秀", ("itzy_zaobao",)),
    MemberName(("ITZY",), "Ryujin", "2001-04-17", "申留真", ("itzy_zaobao",)),
    MemberName(("ITZY",), "Yeji", "2000-05-26", "黄礼志", ("itzy_zaobao",)),
    MemberName(("ITZY",), "Yuna", "2003-12-09", "申有娜", ("itzy_zaobao",)),
    MemberName(("Stray Kids", "3RACHA"), "Bang Chan", "1997-10-03", "方灿", ("straykids_zaobao",)),
    MemberName(("Stray Kids", "3RACHA"), "Changbin", "1999-08-11", "彰彬", ("straykids_zaobao",)),
    MemberName(("Stray Kids",), "Hyunjin", "2000-03-20", "铉辰", ("straykids_zaobao",)),
    MemberName(("Stray Kids",), "Seungmin", "2000-09-22", "昇玟", ("straykids_zaobao",)),
    MemberName(("LE SSERAFIM",), "Hong Eunchae", "2006-11-10", "洪恩采", ("lesserafim_vogue",)),
    MemberName(("LE SSERAFIM",), "Huh Yunjin", "2001-10-08", "许允真", ("lesserafim_vogue",)),
    MemberName(("LE SSERAFIM",), "Kazuha", "2003-08-09", "中村一叶", ("lesserafim_vogue",)),
    MemberName(("LE SSERAFIM", "IZ*ONE"), "Kim Chaewon", "2000-08-01", "金采源", ("lesserafim_vogue", "izone_lesserafim")),
    MemberName(("LE SSERAFIM", "IZ*ONE"), "Sakura", "1998-03-19", "宫胁咲良", ("lesserafim_zaobao", "izone_lesserafim")),
)


def _key(value):
    # 保留重音、标点和内部空格，避免短艺名/相似团名发生模糊命中。
    return unicodedata.normalize("NFC", value.strip()).casefold() if isinstance(value, str) else ""


def _build_index(records):
    index = {}
    for record in records:
        for group in record.groups:
            key = (_key(group), _key(record.name))
            if key in index:
                raise ValueError(f"Duplicate birthday name identity: {group} / {record.name}")
            index[key] = record
    return index


_INDEX = _build_index(MEMBER_NAMES)


def member_name_zh(group, name, birth=None):
    """返回核验过的常用中文名；未知、模糊匹配或生日冲突均返回空串。"""
    record = _INDEX.get((_key(group), _key(name)))
    if record is None or (birth not in (None, "") and birth != record.birth):
        return ""
    return record.zh
