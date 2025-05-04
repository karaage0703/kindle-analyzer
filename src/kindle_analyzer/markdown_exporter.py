"""Kindleの蔵書情報をマークダウン形式で書き出すモジュール。

このモジュールは、Kindleの蔵書情報をSQLiteデータベースから読み取り、
マークダウン形式でファイルに書き出す機能を提供します。
"""

import pandas as pd
import sqlite3
from pathlib import Path
from typing import Union, Optional
from .analyzer import connect_to_database, load_book_data, extract_metadata_attributes, clean_and_convert_dates


def export_books_to_markdown(
    db_path: Union[str, Path],
    output_path: Union[str, Path],
    sort_by: str = "purchase_date",
    ascending: bool = False,
    limit: Optional[int] = None,
) -> None:
    """書籍のリストをマークダウン形式で書き出す。

    Args:
        db_path: データベースファイルのパス
        output_path: 出力ファイルのパス
        sort_by: ソートするカラム名（デフォルト: "purchase_date"）
        ascending: 昇順にソートするかどうか（デフォルト: False）
        limit: 出力する書籍数の上限（デフォルト: None）
    """
    # データベースに接続
    conn = connect_to_database(db_path)

    # 書籍データを読み込む
    book_df = load_book_data(conn)

    # メタデータを抽出
    book_df = extract_metadata_attributes(book_df)

    # 日付を変換
    book_df = clean_and_convert_dates(book_df)

    # 接続を閉じる
    conn.close()

    # 必要なカラムを選択
    columns = ["title_from_metadata", "author", "publisher", "purchase_date", "publication_date", "content_tag"]
    selected_df = book_df[columns].copy()

    # 日付カラムを文字列に変換（タイムゾーン情報なし）
    for date_col in ["purchase_date", "publication_date"]:
        if date_col in selected_df.columns:
            # 日付カラムを文字列に変換
            selected_df[date_col] = selected_df[date_col].astype(str)
            # タイムゾーン情報を削除
            selected_df[date_col] = selected_df[date_col].str.split(" ").str[0]

    # NaN値を処理
    selected_df = selected_df.fillna("不明")

    # ソート
    if sort_by in selected_df.columns:
        selected_df = selected_df.sort_values(by=sort_by, ascending=ascending)

    # 上限を適用
    if limit is not None and limit > 0:
        selected_df = selected_df.head(limit)

    # マークダウン形式で書き出し
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Kindle蔵書リスト\n\n")

        # 書籍数を書き出し
        f.write(f"合計: {len(selected_df)}冊\n\n")

        # 各書籍の情報を書き出し
        for i, (_, row) in enumerate(selected_df.iterrows(), 1):
            title = row["title_from_metadata"]
            author = row["author"]
            publisher = row["publisher"]
            purchase_date = row["purchase_date"]
            publication_date = row["publication_date"]
            content_tag = row["content_tag"]

            f.write(f"## {i}. {title}\n\n")
            f.write(f"- **著者**: {author}\n")
            f.write(f"- **出版社**: {publisher}\n")
            f.write(f"- **購入日**: {purchase_date}\n")
            f.write(f"- **出版日**: {publication_date}\n")

            if content_tag != "不明":
                f.write(f"- **タグ**: {content_tag}\n")

            f.write("\n---\n\n")

    print(f"書籍リストをマークダウン形式で {output_path} に書き出しました。")


def main():
    """コマンドラインから実行するためのエントリーポイント。"""
    import argparse

    parser = argparse.ArgumentParser(description="Kindleの蔵書情報をマークダウン形式で書き出すツール")

    parser.add_argument("--db-path", "-d", type=str, required=True, help="SQLiteデータベースファイルのパス")

    parser.add_argument(
        "--output", "-o", type=str, default="kindle_books.md", help="出力ファイルのパス（デフォルト: kindle_books.md）"
    )

    parser.add_argument(
        "--sort-by",
        "-s",
        type=str,
        default="purchase_date",
        choices=["title_from_metadata", "author", "publisher", "purchase_date", "publication_date"],
        help="ソートするカラム名（デフォルト: purchase_date）",
    )

    parser.add_argument("--ascending", "-a", action="store_true", help="昇順にソートする（デフォルト: 降順）")

    parser.add_argument("--limit", "-l", type=int, default=None, help="出力する書籍数の上限")

    args = parser.parse_args()

    export_books_to_markdown(
        db_path=args.db_path, output_path=args.output, sort_by=args.sort_by, ascending=args.ascending, limit=args.limit
    )


if __name__ == "__main__":
    main()
