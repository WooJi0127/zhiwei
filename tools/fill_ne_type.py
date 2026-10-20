# -*- coding: utf-8 -*-
"""一次性补录：把网易云自己标的类型（Single/EP/专辑）回填进 rtype_src，再重判 rtype。"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build  # noqa: E402


def main():
    con = build.get_db()
    cur = con.cursor()
    print("== 回填前 ==")
    for row in cur.execute(
        "SELECT source, COUNT(*), SUM(CASE WHEN COALESCE(rtype,'')<>'' THEN 1 ELSE 0 END)"
        " FROM releases GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"  {row[0]:10s} {row[1]:5d} 条, 有类型 {row[2]}")

    build.step_netease_tracks(con, cap=9999)
    build.step_retype(con)
    con.commit()

    print("== 回填后 ==")
    for row in cur.execute(
        "SELECT source, COUNT(*), SUM(CASE WHEN COALESCE(rtype,'')<>'' THEN 1 ELSE 0 END)"
        " FROM releases GROUP BY 1 ORDER BY 2 DESC"
    ):
        t, ty = row[1], row[2]
        print(f"  {row[0]:10s} {t:5d} 条, 有类型 {ty:5d} ({100*ty/t:.0f}%)")

    print("\n== rtype_src 分布 ==")
    for row in cur.execute(
        "SELECT COALESCE(rtype_src,'(空)'), COUNT(*) FROM releases"
        " GROUP BY 1 ORDER BY 2 DESC LIMIT 15"
    ):
        print(f"  {row[0]:16s} {row[1]}")

    con.close()


if __name__ == "__main__":
    main()
