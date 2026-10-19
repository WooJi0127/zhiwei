# -*- coding: utf-8 -*-
"""
冒烟测试：用无头浏览器真实点一遍界面，确认核心功能没坏。

改完 core/ 之后跑一次，比肉眼看快得多，也能防止「改了 A 坏了 B」。

    python tools/smoke_test.py            # 测 core/index.html（各端真正用的那份）
    python tools/smoke_test.py --single   # 改测 知未.html（内联版）

依赖 Edge（Windows 自带）。找不到会自动跳过并提示。
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

INJECT = r"""
<script>
var LOG = [];
var HW = [];
function $(i){ return document.getElementById(i); }
function QT(){ return document.querySelectorAll("#content .card").length; }
function vis(id){ return getComputedStyle($(id)).display !== "none"; }
function ext(){ return document.querySelectorAll("#content a[href^='http'], #detailView a[href^='http']").length; }
function txt(sel){ var e = document.querySelector(sel); return e ? e.textContent.trim() : "?"; }

var steps = [], i = 0;
function step(f){ steps.push(f); }

step(function(){
  LOG.push("默认页=首页:" + ($("homeView").style.display !== "none")
    + " tab高亮=" + (document.querySelector(".tab.on") || {}).textContent);
  document.querySelector('[data-tab="past"]').click();
});
/* 数据分片：主文件只带近一年，更早的按年份切片按需加载 */
step(function(){
  var md = (window.__KPOP_DATA__ || {});
  LOG.push("分片: 主文件发行=" + (md.releases || []).length
    + " 待加载年份=" + JSON.stringify(md.years || {})
    + " 年份按钮=" + document.querySelectorAll(".ybtn").length
    + " 初始卡片=" + QT());
  var b = document.querySelector(".ybtn");
  if(b) b.click();
});
step(function(){});
step(function(){});
step(function(){
  LOG.push("点一年份后: 剩余按钮=" + document.querySelectorAll(".ybtn").length
    + " 卡片=" + QT());
});
step(function(){
  LOG.push("默认范围=" + QT());
  $("dateBtn").click();
});
step(function(){
  var b = document.querySelector('[data-quick="pall"]');
  if(!b){ LOG.push("ERR:日历里没有「全部已发布」"); return; }
  b.click();
});
step(function(){
  LOG.push("全部已发布=" + QT() + " label=" + $("dateLabel").textContent);
  $("q").value = "A2O"; $("q").dispatchEvent(new Event("input"));
});
step(function(){
  LOG.push("搜索A2O=" + QT());
  LOG.push("标题=" + JSON.stringify(Array.prototype.map.call(
    document.querySelectorAll("#content .ctitle"),
    function(e){ return e.textContent.trim(); }).slice(0, 8)));
  $("qclr").click();
});
step(function(){
  LOG.push("列表无外链=" + (ext() === 0));
  document.querySelector('[data-tab="future"]').click();
});
step(function(){
  LOG.push("未来7天=" + QT() + " 子条=" + vis("upBar"));
  document.querySelector('[data-up="month"]').click();
});
step(function(){
  LOG.push("本月=" + QT());
  document.querySelector('[data-up="nmonth"]').click();
});
step(function(){
  LOG.push("下月=" + QT());
  document.querySelector('[data-tab="mine"]').click();
});
step(function(){
  LOG.push("我的·收藏=" + QT() + " 子条=" + vis("mineBar"));
  document.querySelector('[data-mine="bias"]').click();
});
step(function(){
  LOG.push("我的·本命=" + QT() + " biasBox=" + vis("biasBox"));
  document.querySelector('[data-tab="past"]').click();
});
step(function(){
  LOG.push("全部发布=" + QT() + " filters=" + vis("filters"));
  var c = {};
  Array.prototype.forEach.call($("fKind").options, function(o){
    if(!o.value) return;
    $("fKind").value = o.value;
    $("fKind").dispatchEvent(new Event("change"));
    c[o.value] = QT();
  });
  LOG.push("艺人分类=" + JSON.stringify(c));
  $("fKind").value = ""; $("fKind").dispatchEvent(new Event("change"));
});
step(function(){
  var t = {};
  Array.prototype.forEach.call($("fType").options, function(o){
    if(!o.value) return;
    $("fType").value = o.value;
    $("fType").dispatchEvent(new Event("change"));
    t[o.value] = QT();
  });
  LOG.push("发行类型=" + JSON.stringify(t));
  $("fType").value = ""; $("fType").dispatchEvent(new Event("change"));
});
step(function(){ document.querySelector("#content .card").click(); });
step(function(){
  LOG.push("详情=" + ($("detailView").style.display !== "none")
    + " 来源=" + txt(".dsrc")
    + " 无外链=" + (ext() === 0)
    + " 曲目行=" + document.querySelectorAll("#detailView .trk").length);
  $("backBtn").click();
});
step(function(){ LOG.push("返回=" + ($("detailView").style.display === "none")); });

/* 首页（默认页）：含今天发行 / 今天生日 / 打歌节目 / 即将回归 */
step(function(){ document.querySelector('[data-view="home"]').click(); });
step(function(){
  LOG.push("首页可见=" + ($("homeView").style.display !== "none")
    + " 列表页隐藏=" + ($("listView").style.display === "none")
    + " 板块数=" + document.querySelectorAll("#homeView .hsec").length
    + " 概览=" + (document.querySelector("#homeView .hsum") || {}).textContent);
  LOG.push("生日条数=" + document.querySelectorAll("#homeView .bday").length
    + " 迷你卡=" + document.querySelectorAll("#homeView .mini").length
    + " 首页打歌条=" + (document.querySelector("#homeShows .shnow") ? "有" : "无"));
  var mm = (window.__KPOP_DATA__ && window.__KPOP_DATA__.members) || [];
  var md = new Date(); var key = ("0" + (md.getMonth()+1)).slice(-2) + "-" + ("0" + md.getDate()).slice(-2);
  var exp = mm.filter(function(x){ return x.b && x.b.slice(5) === key; }).length;
  LOG.push("members=" + mm.length + " 今天应过生日=" + exp
    + " 生日区=" + ((document.querySelector("#homeView .bdaylist") || document.querySelectorAll("#homeView .hempty")[1] || {}).textContent || "").trim().slice(0, 20));
  $("toCal").click();
});
step(function(){
  LOG.push("跳转日历后 首页=" + ($("homeView").style.display === "none")
    + " 列表页=" + ($("listView").style.display !== "none")
    + " 高亮tab=" + (document.querySelector(".tab.on") || {}).textContent);
  document.querySelector('[data-view="home"]').click();
});
step(function(){
  LOG.push("回首页=" + ($("homeView").style.display !== "none")
    + " 高亮tab=" + (document.querySelector(".tab.on") || {}).textContent);
  document.querySelector('[data-tab="future"]').click();
});

/* 打歌节目只属于「更多」页，不该混进收藏 / 本命这些筛选视图
   （showsBar 只在「更多」页渲染，其它页是空的，所以要先切过去） */
step(function(){ document.querySelector('[data-tab="mine"]').click(); });
step(function(){
  LOG.push("收藏页打歌条=" + getComputedStyle($("showsBar")).display);
  document.querySelector('[data-tab="more"]').click();
});
step(function(){
  LOG.push("更多页打歌条=" + getComputedStyle($("showsBar")).display
    + " 今日行=" + (document.querySelectorAll("#showsBar .shrow").length));
  var b = document.querySelector("#showsBar [data-showtoggle]");
  if(b) b.click();
});
step(function(){
  LOG.push("更多页展开=" + getComputedStyle(document.querySelector("#showsBar .shweek")).display);
});

/* 首页的开关必须真的能展开（以前只刷了日历页那份，点了像没反应）。
   连点三次，验证「开→关→开」都能生效 */
step(function(){ document.querySelector('[data-view="home"]').click(); });
step(function(){
  HW = [getComputedStyle(document.querySelector("#homeShows .shweek")).display];
  document.querySelector("#homeShows [data-showtoggle]").click();
});
step(function(){
  HW.push(getComputedStyle(document.querySelector("#homeShows .shweek")).display);
  document.querySelector("#homeShows [data-showtoggle]").click();
});
step(function(){
  HW.push(getComputedStyle(document.querySelector("#homeShows .shweek")).display);
  LOG.push("首页开关=" + HW.join("/") + " 有效=" + (HW[0] !== HW[1] && HW[0] === HW[2]));
});


step(function(){ document.querySelector('[data-view="home"]').click(); });
step(function(){
  LOG.push("首页板块=" + Array.prototype.map.call(
    document.querySelectorAll("#homeView .hsec-h h2"),
    function(e){ return e.textContent.trim(); }).join("/"));
  LOG.push("今日生日默认=" + document.querySelectorAll("#homeView .bday").length
    + " 展开按钮=" + ($("bdMore") ? "有" : "无"));
  var b = $("bdMore"); if(b) b.click();
});
step(function(){
  LOG.push("展开后=" + document.querySelectorAll("#homeView .bday").length);
});
/* 自定义下拉：点开面板并选一项，值要同步回底层 select */
step(function(){ document.querySelector('[data-tab="past"]').click(); });
step(function(){
  LOG.push("下拉自绘=" + (document.querySelectorAll(".selbtn").length)
    + " 原生select隐藏=" + (getComputedStyle($("fType")).display));
  var b = document.querySelector(".selbtn"); if(b) b.click();
});
step(function(){
  var pop = document.querySelector(".selpop.on");
  LOG.push("面板打开=" + !!pop + " 选项数=" + (pop ? pop.querySelectorAll(".selopt").length : 0));
  var o = pop && pop.querySelectorAll(".selopt")[2];
  if(o) o.click();
});
step(function(){
  LOG.push("选中后 select值=" + $("fType").value
    + " 面板关闭=" + (document.querySelectorAll(".selpop.on").length === 0));
});
/* 下载页已移除 */
step(function(){
  LOG.push("下载入口=" + ($("dlBtn") ? "仍在" : "已移除")
    + " 下载页=" + ($("dlView") ? "仍在" : "已移除"));
});

function next(){
  if(i >= steps.length){
    var d = document.createElement("div");
    d.id = "TESTOUT";
    d.textContent = "@@" + LOG.join(" ||| ") + "@@";
    document.body.appendChild(d);
    return;
  }
  var fn = steps[i++];
  try { fn(); } catch(e){ LOG.push("ERR@step" + i + ":" + e.message); }
  setTimeout(next, 320);   // 大于搜索框 170ms 的防抖，等 render 跑完再断言
}
setTimeout(next, 400);
</script>
"""

# 这些断言不过就说明坏了
REQUIRED = [
    ("列表无外链=true",  "卡片里出现了外链"),
    ("无外链=true",      "详情页里有外链"),
    ("详情=true",        "详情页打不开"),
    ("返回=true",        "详情页返回不了"),
    ("搜索A2O=7",        "A2O 收录数不对（应为 7 张）"),
]


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def main():
    single = "--single" in sys.argv
    src = os.path.join(ROOT, "知未.html") if single else os.path.join(CORE, "index.html")
    if not os.path.isfile(src):
        sys.exit(f"找不到 {src}")

    edge = find_edge()
    if not edge:
        print("! 没找到 Microsoft Edge，跳过冒烟测试")
        return 0

    tmp = tempfile.mkdtemp(prefix="zwtest_")
    try:
        # 测试页必须和它引用的资源（app.js / app.css / data/）同目录。
        # core/index.html 是外链版，少复制一个就会整页空白，所以这里整个目录搬过去。
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        srcdir = os.path.dirname(src)
        for name in os.listdir(srcdir):
            s = os.path.join(srcdir, name)
            d = os.path.join(work, name)
            if name == "index.html":
                continue
            shutil.copy2(s, d) if os.path.isfile(s) else shutil.copytree(s, d)

        page = io.open(src, encoding="utf-8").read()
        io.open(os.path.join(work, "index.html"), "w", encoding="utf-8").write(
            page.replace("</body>", INJECT + "\n</body>"))

        # 数据统一取自 data/data.js，保证测的是线上那份
        if not os.path.isdir(os.path.join(work, "data")):
            shutil.copytree(os.path.join(ROOT, "data"), os.path.join(work, "data"))

        prof = os.path.join(tmp, "profile")
        dom = os.path.join(tmp, "dom.html")
        pic = "file:///" + os.path.join(work, "index.html").replace("\\", "/")

        # 无头浏览器偶尔会因为 GPU 进程起不来而卡住，多试几次基本都能过。
        # 这台机器上光启动 Edge 就可能要 40 秒（没有 GPU），加上注入脚本要
        # 反复重渲染 1700 张卡片，慢的时候整轮能到 6~7 分钟，所以超时给得很宽。
        # 注意：别加 --disable-features=VizDisplayCompositor / --disable-software-rasterizer，
        # 这两个会让 --dump-dom 直接卡死。
        ok = False
        for attempt in (1, 2):
            t0 = time.time()
            try:
                with io.open(dom, "w", encoding="utf-8") as fh:
                    subprocess.run(
                        [edge, "--headless=new", "--disable-gpu", "--no-sandbox",
                         "--virtual-time-budget=20000", "--window-size=1400,1000",
                         f"--user-data-dir={prof}{attempt}", "--dump-dom", pic],
                        stdout=fh, stderr=subprocess.DEVNULL, timeout=480)
                ok = True
                print(f"  · 页面渲染完成，用时 {time.time()-t0:.0f}s")
                break
            except subprocess.TimeoutExpired:
                print(f"  · Edge 第 {attempt} 次超时（{time.time()-t0:.0f}s），重试…")
        if not ok:
            print("! Edge 起不来，跳过（换个时间重试即可，一般是环境忙）")
            return 1

        html = io.open(dom, encoding="utf-8", errors="ignore").read()
        m = re.search(r'<div id="TESTOUT">(.*?)</div>', html, re.S)
        if not m:
            print("! 测试脚本没跑完（页面可能报错了）")
            return 1

        out = m.group(1)
        print(f"--- {os.path.relpath(src, ROOT)} ---")
        for line in out.split(" ||| "):
            print("  " + line.strip())

        bad = [msg for pat, msg in REQUIRED if pat not in out]
        print()
        if bad:
            for msg in bad:
                print("  ✗ " + msg)
            if "ERR@" in out:
                print("  页面内有 JS 报错，见上方 ERR@ 行")
            return 1
        print("  ✓ 全部断言通过")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
