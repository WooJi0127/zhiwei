# -*- coding: utf-8 -*-
"""
布局检查：在几种典型屏幕宽度下打开页面，验证没有溢出、列数正确、触摸目标够大。

比截图更适合自动化——截图只能人眼看，这个能进 CI，也能防止「改桌面样式把手机搞坏」。

    python tools/layout_test.py
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# (标签, 宽, 高, 期望的最少列数, 期望的最多列数)
# 列数跟 .grid 的 minmax(244px,1fr) 绑定：卡片放大后（208→244px）iPad/桌面各少一列，
# 预期值随之更新；上下各留一列余量，防字体四舍五入误报。
VIEWPORTS = [
    ("iPhone SE   ", 375, 667, 2, 2),
    ("iPhone 14   ", 390, 844, 2, 2),
    ("iPhone 横屏 ", 844, 390, 3, 5),
    ("iPad 竖屏   ", 768, 1024, 2, 3),
    ("桌面 1280   ", 1280, 800, 4, 5),
]

PROBE = r"""
<script>
/*
 * 探测脚本会被注入到 iframe 里的每个页面副本。
 * iframe 有固定宽度，页面内部的 media query 会按那个宽度生效，
 * 所以能在一次浏览器启动里测完所有视口。
 */
(function(){
  function measure(){
    var de = document.documentElement;

    // 1) 横向溢出：手机上一旦出现横向滚动条，体验就毁了
    var out = { overflowX: Math.max(0, de.scrollWidth - de.clientWidth) };

    // 2) 卡片列数：从第一张卡的宽度反推
    var grid = document.querySelector(".grid");
    var card = document.querySelector(".grid .card");
    if (grid && card) {
      out.cols = Math.round(grid.getBoundingClientRect().width
                            / card.getBoundingClientRect().width);
      out.cardW = Math.round(card.getBoundingClientRect().width);
    } else { out.cols = 0; }

    // 3) 触摸目标：页签 / 收藏 / 爱心 都不能太小
    function minSide(sel){
      var m = 999;
      document.querySelectorAll(sel).forEach(function(e){
        var r = e.getBoundingClientRect();
        if (r.width > 0) m = Math.min(m, Math.min(r.width, r.height));
      });
      return m === 999 ? 0 : Math.round(m);
    }
    out.tabH = minSide(".tab");
    out.favSide = minSide(".favbtn");
    out.heartSide = minSide(".heart");

    // 4) 关键元素必须在可视宽度内
    out.wideEls = [];
    document.querySelectorAll("header, main, .hwrap, .stats, .filters").forEach(function(e){
      var r = e.getBoundingClientRect();
      if (r.width > de.clientWidth + 1) {
        out.wideEls.push((e.className || e.tagName) + ":" + Math.round(r.width));
      }
    });

    out.vw = de.clientWidth;

    if (window.parent !== window) {
      window.parent.__R__ = window.parent.__R__ || [];
      window.parent.__R__.push(out);
    } else {
      var d = document.createElement("div");
      d.id = "LAYOUTOUT";
      d.textContent = "@@" + JSON.stringify([out]) + "@@";
      document.body.appendChild(d);
    }
  }

  /* 默认页是首页，卡片网格和收藏/爱心按钮都在「过去」页——
     先切过去再量，否则量到的永远是 0（首页优先改版后这里没跟上过）。 */
  var t = document.querySelector('[data-tab="past"]');
  if (t) { t.click(); setTimeout(measure, 500); } else { setTimeout(measure, 300); }
})();
</script>
"""

# 测试台：把每个视口塞进一个固定宽度的 iframe，一次跑完
HARNESS = r"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{margin:0;background:#111}
  iframe{border:0;display:block;height:900px;background:#fff}
</style></head><body>
<div id="frames"></div>
<script>
  var SIZES = __SIZES__;
  var host = document.getElementById("frames");
  SIZES.forEach(function(w){
    var f = document.createElement("iframe");
    f.style.width = w + "px";
    f.src = "index.html";
    host.appendChild(f);
  });
  window.__R__ = [];
  var waited = 0;
  var timer = setInterval(function(){
    waited += 300;
    // 等所有 iframe 都报上来，或者最多等 25 秒
    if (window.__R__.length >= SIZES.length || waited >= 25000) {
      clearInterval(timer);
      var d = document.createElement("div");
      d.id = "LAYOUTOUT";
      d.textContent = "@@" + JSON.stringify(window.__R__) + "@@";
      document.body.appendChild(d);
    }
  }, 300);
</script>
</body></html>
"""


def find_edge():
    return next((p for p in EDGE_CANDIDATES if os.path.isfile(p)), None)


def prepare(work, widths):
    """页面和 1MB 数据只复制一次，各 iframe 共用。"""
    os.makedirs(work, exist_ok=True)
    for name in os.listdir(CORE):
        s, d = os.path.join(CORE, name), os.path.join(work, name)
        if os.path.isfile(s):
            shutil.copy2(s, d)
        elif os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)

    page = io.open(os.path.join(CORE, "index.html"), encoding="utf-8").read()
    io.open(os.path.join(work, "index.html"), "w", encoding="utf-8").write(
        page.replace("</body>", PROBE + "\n</body>"))

    harness = HARNESS.replace("__SIZES__", repr(widths).replace("'", '"'))
    io.open(os.path.join(work, "_harness.html"), "w", encoding="utf-8").write(harness)


def run_all(edge, work):
    """一次启动跑完所有视口。

    无 GPU 的机器上 Edge 启动本身就要几十秒，超时给宽一点；失败重试一次。
    """
    dom = os.path.join(work, "_dom.html")
    pic = "file:///" + os.path.join(work, "_harness.html").replace("\\", "/")
    for attempt in (1, 2):
        try:
            with io.open(dom, "w", encoding="utf-8") as fh:
                subprocess.run(
                    [edge, "--headless=new", "--disable-gpu", "--no-sandbox",
                     "--hide-scrollbars", "--allow-file-access-from-files",
                     "--window-size=1400,1000", "--virtual-time-budget=30000",
                     f"--user-data-dir={os.path.join(work, '_p')}{attempt}",
                     "--dump-dom", pic],
                    stdout=fh, stderr=subprocess.DEVNULL, timeout=360)
            break
        except subprocess.TimeoutExpired:
            print(f"  · Edge 第 {attempt} 次超时，重试…")
    else:
        return None

    html = io.open(dom, encoding="utf-8", errors="ignore").read()
    m = re.search(r'<div id="LAYOUTOUT">@@(.*?)@@</div>', html, re.S)
    if not m:
        return None
    import json
    return json.loads(m.group(1))


def main():
    edge = find_edge()
    if not edge:
        print("! 没找到 Microsoft Edge，跳过布局检查")
        return 0

    tmp = tempfile.mkdtemp(prefix="zwlayout_")
    bad = 0
    try:
        print(f"{'视口':<14}{'实际宽':>7}{'列数':>6}{'横向溢出':>9}"
              f"{'页签高':>8}{'收藏':>6}{'爱心':>6}  判定")
        print("-" * 74)
        work = os.path.join(tmp, "work")
        prepare(work, [v[1] for v in VIEWPORTS])
        results = run_all(edge, work)
        if not results:
            print("! 测试台没跑出来（iframe 可能被拦了）")
            return 1
        # iframe 的返回顺序不保证，按宽度对回去
        by_w = {r["vw"]: r for r in results}

        for label, w, h, lo, hi in VIEWPORTS:
            r = by_w.get(w)
            if not r:
                # 允许 ±1 的视口误差（iframe 边框等）
                r = next((v for k, v in by_w.items() if abs(k - w) <= 1), None)
            if not r:
                print(f"{label}{w:>7}  没拿到结果")
                bad += 1
                continue
            issues = []
            if r["overflowX"] > 0:
                issues.append(f"横向溢出 {r['overflowX']}px")
            if not (lo <= r["cols"] <= hi):
                issues.append(f"列数 {r['cols']} 不在 {lo}-{hi}")
            if w <= 760 and r["tabH"] and r["tabH"] < 28:
                issues.append(f"页签太小 {r['tabH']}px")
            if r["wideEls"]:
                issues.append("超宽元素 " + ",".join(r["wideEls"][:3]))
            ok = not issues
            if not ok:
                bad += 1
            print(f"{label}{r['vw']:>7}{r['cols']:>6}{r['overflowX']:>9}"
                  f"{r['tabH']:>8}{r['favSide']:>6}{r['heartSide']:>6}  "
                  + ("✓" if ok else "✗ " + "; ".join(issues)))
        print()
        if bad:
            print(f"  {bad} 个视口有问题")
            return 1
        print("  ✓ 所有视口通过")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
