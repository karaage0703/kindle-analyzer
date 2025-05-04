"""Kindleの蔵書情報を分析するモジュール。

このモジュールは、Kindleの蔵書情報をSQLiteデータベースから読み取り、
分析および可視化するための機能を提供します。
"""

import pandas as pd
import sqlite3
import plistlib
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Any, Dict, Union

# 日本語フォントの設定
# macOSの場合はヒラギノ、Windowsの場合はMSゴシック、それ以外の場合はIPAフォントを使用
import platform

if platform.system() == "Darwin":  # macOS
    plt.rcParams["font.family"] = "Hiragino Sans GB"
elif platform.system() == "Windows":  # Windows
    plt.rcParams["font.family"] = "MS Gothic"
else:  # Linux等
    plt.rcParams["font.family"] = "IPAGothic"


def connect_to_database(db_path: Union[str, Path]) -> sqlite3.Connection:
    """SQLiteデータベースに接続する。

    Args:
        db_path: データベースファイルのパス

    Returns:
        sqlite3.Connection: データベース接続オブジェクト
    """
    return sqlite3.connect(db_path)


def load_book_data(conn: sqlite3.Connection) -> pd.DataFrame:
    """ZBOOKテーブルからデータを読み込む。

    Args:
        conn: データベース接続オブジェクト

    Returns:
        pd.DataFrame: 書籍データのDataFrame
    """
    return pd.read_sql_query("SELECT * FROM ZBOOK", conn)


def resolve_ns_keyed_archive_fully(data: bytes) -> Any:
    """ZSYNCMETADATAATTRIBUTESカラムのplistデータを解析する。

    Args:
        data: バイナリ形式のplistデータ

    Returns:
        Any: 解析されたデータ
    """
    if pd.isna(data):
        return np.nan

    try:
        root = plistlib.loads(data)
        objects = root["$objects"]
        top_uid = root["$top"]["root"]

        # クラスID → クラス名
        class_map = {
            idx: obj["$classname"] for idx, obj in enumerate(objects) if isinstance(obj, dict) and "$classname" in obj
        }

        def resolve(obj: Any, memo: Dict[int, Any]) -> Any:
            if isinstance(obj, plistlib.UID):
                idx = obj.data
                if idx in memo:
                    return memo[idx]
                raw = objects[idx]
                resolved = resolve(raw, memo)
                memo[idx] = resolved
                return resolved

            elif isinstance(obj, list):
                return [resolve(item, memo) for item in obj]

            elif isinstance(obj, dict):
                # クラスID に基づいて判定
                class_id = obj.get("$class")
                class_name = class_map.get(class_id.data) if isinstance(class_id, plistlib.UID) else None

                # NSMutableArray / NSArray の展開
                if class_name in ("NSMutableArray", "NSArray") and "NS.objects" in obj:
                    return resolve(obj["NS.objects"], memo)

                # NSMutableDictionary / NSDictionary の展開
                if class_name in ("NSMutableDictionary", "NSDictionary") and "NS.keys" in obj and "NS.objects" in obj:
                    keys = resolve(obj["NS.keys"], memo)
                    vals = resolve(obj["NS.objects"], memo)
                    return dict(zip(keys, vals))

                # 通常の辞書展開
                return {
                    resolve(k, memo): resolve(v, memo)
                    for k, v in obj.items()
                    if not (isinstance(k, str) and k.startswith("$"))
                }

            else:
                return obj

        return resolve(top_uid, {})
    except Exception as e:
        print(f"Error parsing plist data: {e}")
        return np.nan


def extract_metadata_attributes(book_df: pd.DataFrame) -> pd.DataFrame:
    """ZSYNCMETADATAATTRIBUTESカラムからメタデータを抽出する。

    Args:
        book_df: 書籍データのDataFrame

    Returns:
        pd.DataFrame: メタデータを含む拡張されたDataFrame
    """
    # ZSYNCMETADATAATTRIBUTESカラムがない場合は元のDataFrameを返す
    if "ZSYNCMETADATAATTRIBUTES" not in book_df.columns:
        print("ZSYNCMETADATAATTRIBUTES column not found in the DataFrame")
        return book_df

    # メタデータを解析
    book_df["metadata"] = book_df["ZSYNCMETADATAATTRIBUTES"].apply(resolve_ns_keyed_archive_fully)

    # 必要な情報を抽出
    def extract_attribute(row, attr_path):
        if pd.isna(row["metadata"]):
            return np.nan

        try:
            value = row["metadata"]
            for key in attr_path:
                if key in value:
                    value = value[key]
                else:
                    return np.nan

            # リスト型の値を文字列に変換
            if isinstance(value, list):
                return ", ".join(str(item) for item in value)

            return value
        except (KeyError, TypeError, ValueError, AttributeError):
            return np.nan

    # 著者情報を抽出
    book_df["author"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "authors", "author"]), axis=1)

    # 出版社情報を抽出
    book_df["publisher"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "publishers", "publisher"]), axis=1)

    # タイトル情報を抽出
    book_df["title_from_metadata"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "title"]), axis=1)

    # ASIN情報を抽出
    book_df["asin"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "ASIN"]), axis=1)

    # コンテンツタグ情報を抽出
    book_df["content_tag"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "content_tags", "tag"]), axis=1)

    # 購入日情報を抽出
    book_df["purchase_date"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "purchase_date"]), axis=1)

    # 出版日情報を抽出
    book_df["publication_date"] = book_df.apply(lambda row: extract_attribute(row, ["attributes", "publication_date"]), axis=1)

    return book_df


def clean_and_convert_dates(df: pd.DataFrame) -> pd.DataFrame:
    """日付カラムをdatetime型に変換する。

    Args:
        df: 処理対象のDataFrame

    Returns:
        pd.DataFrame: 日付が変換されたDataFrame
    """
    date_columns = ["purchase_date", "publication_date"]

    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df


def analyze_books_by_year(df: pd.DataFrame, date_column: str = "purchase_date") -> pd.DataFrame:
    """年ごとの書籍数を集計する。

    Args:
        df: 書籍データのDataFrame
        date_column: 集計に使用する日付カラム名

    Returns:
        pd.DataFrame: 年ごとの書籍数
    """
    if date_column not in df.columns:
        raise ValueError(f"Column {date_column} not found in DataFrame")

    # 年を抽出
    df["year"] = df[date_column].dt.year

    # 年ごとに集計
    yearly_counts = df.groupby("year").size().reset_index(name="count")

    return yearly_counts


def plot_books_by_year(yearly_counts: pd.DataFrame, title: str = "年ごとの書籍数") -> plt.Figure:
    """年ごとの書籍数をプロットする。

    Args:
        yearly_counts: 年ごとの書籍数のDataFrame
        title: グラフのタイトル

    Returns:
        plt.Figure: プロットされた図
    """
    plt.figure(figsize=(12, 6))
    ax = sns.barplot(x="year", y="count", data=yearly_counts)

    # 各バーの上に数値を表示
    for i, v in enumerate(yearly_counts["count"]):
        ax.text(i, v + 0.5, str(v), ha="center")

    plt.title(title, fontsize=16)
    plt.xlabel("年", fontsize=12)
    plt.ylabel("書籍数", fontsize=12)
    plt.xticks(rotation=45)
    plt.tight_layout()

    return plt.gcf()


def analyze_books_by_publisher(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """出版社ごとの書籍数を集計する。

    Args:
        df: 書籍データのDataFrame
        top_n: 表示する上位出版社の数

    Returns:
        pd.DataFrame: 出版社ごとの書籍数
    """
    if "publisher" not in df.columns:
        raise ValueError("Column 'publisher' not found in DataFrame")

    # 出版社ごとに集計
    publisher_counts = df["publisher"].value_counts().reset_index()
    publisher_counts.columns = ["publisher", "count"]

    # 上位N社を抽出
    top_publishers = publisher_counts.head(top_n)

    return top_publishers


def plot_books_by_publisher(publisher_counts: pd.DataFrame, title: str = "出版社ごとの書籍数") -> plt.Figure:
    """出版社ごとの書籍数をプロットする。

    Args:
        publisher_counts: 出版社ごとの書籍数のDataFrame
        title: グラフのタイトル

    Returns:
        plt.Figure: プロットされた図
    """
    plt.figure(figsize=(12, 8))
    ax = sns.barplot(x="count", y="publisher", data=publisher_counts)

    # 各バーの右に数値を表示
    for i, v in enumerate(publisher_counts["count"]):
        ax.text(v + 0.5, i, str(v), va="center")

    plt.title(title, fontsize=16)
    plt.xlabel("書籍数", fontsize=12)
    plt.ylabel("出版社", fontsize=12)
    plt.tight_layout()

    return plt.gcf()


def analyze_books_by_author(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """著者ごとの書籍数を集計する。

    Args:
        df: 書籍データのDataFrame
        top_n: 表示する上位著者の数

    Returns:
        pd.DataFrame: 著者ごとの書籍数
    """
    if "author" not in df.columns:
        raise ValueError("Column 'author' not found in DataFrame")

    # 著者ごとに集計
    author_counts = df["author"].value_counts().reset_index()
    author_counts.columns = ["author", "count"]

    # 上位N人を抽出
    top_authors = author_counts.head(top_n)

    return top_authors


def plot_books_by_author(author_counts: pd.DataFrame, title: str = "著者ごとの書籍数") -> plt.Figure:
    """著者ごとの書籍数をプロットする。

    Args:
        author_counts: 著者ごとの書籍数のDataFrame
        title: グラフのタイトル

    Returns:
        plt.Figure: プロットされた図
    """
    plt.figure(figsize=(12, 8))
    ax = sns.barplot(x="count", y="author", data=author_counts)

    # 各バーの右に数値を表示
    for i, v in enumerate(author_counts["count"]):
        ax.text(v + 0.5, i, str(v), va="center")

    plt.title(title, fontsize=16)
    plt.xlabel("書籍数", fontsize=12)
    plt.ylabel("著者", fontsize=12)
    plt.tight_layout()

    return plt.gcf()


def analyze_books_by_content_tag(df: pd.DataFrame) -> pd.DataFrame:
    """コンテンツタグごとの書籍数を集計する。

    Args:
        df: 書籍データのDataFrame

    Returns:
        pd.DataFrame: コンテンツタグごとの書籍数
    """
    if "content_tag" not in df.columns:
        raise ValueError("Column 'content_tag' not found in DataFrame")

    # コンテンツタグごとに集計
    tag_counts = df["content_tag"].value_counts().reset_index()
    tag_counts.columns = ["content_tag", "count"]

    return tag_counts


def plot_books_by_content_tag(tag_counts: pd.DataFrame, title: str = "コンテンツタグごとの書籍数") -> plt.Figure:
    """コンテンツタグごとの書籍数をプロットする。

    Args:
        tag_counts: コンテンツタグごとの書籍数のDataFrame
        title: グラフのタイトル

    Returns:
        plt.Figure: プロットされた図
    """
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(x="content_tag", y="count", data=tag_counts)

    # 各バーの上に数値を表示
    for i, v in enumerate(tag_counts["count"]):
        ax.text(i, v + 0.5, str(v), ha="center")

    plt.title(title, fontsize=16)
    plt.xlabel("コンテンツタグ", fontsize=12)
    plt.ylabel("書籍数", fontsize=12)
    plt.tight_layout()

    return plt.gcf()


def analyze_monthly_purchases(df: pd.DataFrame) -> pd.DataFrame:
    """月ごとの購入書籍数を集計する。

    Args:
        df: 書籍データのDataFrame

    Returns:
        pd.DataFrame: 月ごとの購入書籍数
    """
    if "purchase_date" not in df.columns:
        raise ValueError("Column 'purchase_date' not found in DataFrame")

    # 年月を抽出（タイムゾーン情報を保持するためにstrftimeを使用）
    df["year_month"] = df["purchase_date"].dt.strftime("%Y-%m")

    # 年月ごとに集計
    monthly_counts = df.groupby("year_month").size().reset_index(name="count")

    return monthly_counts


def plot_monthly_purchases(monthly_counts: pd.DataFrame, title: str = "月ごとの購入書籍数") -> plt.Figure:
    """月ごとの購入書籍数をプロットする。

    Args:
        monthly_counts: 月ごとの購入書籍数のDataFrame
        title: グラフのタイトル

    Returns:
        plt.Figure: プロットされた図
    """
    plt.figure(figsize=(15, 6))
    sns.lineplot(x="year_month", y="count", data=monthly_counts, marker="o")

    plt.title(title, fontsize=16)
    plt.xlabel("年月", fontsize=12)
    plt.ylabel("書籍数", fontsize=12)
    plt.xticks(rotation=90)
    plt.tight_layout()

    return plt.gcf()


def analyze_kindle_library(db_path: Union[str, Path]) -> Dict[str, pd.DataFrame]:
    """Kindleライブラリを分析する。

    Args:
        db_path: データベースファイルのパス

    Returns:
        Dict[str, pd.DataFrame]: 各種分析結果を含む辞書
    """
    # データベースに接続
    conn = connect_to_database(db_path)

    # 書籍データを読み込む
    book_df = load_book_data(conn)

    # メタデータを抽出
    book_df = extract_metadata_attributes(book_df)

    # 日付を変換
    book_df = clean_and_convert_dates(book_df)

    # 年ごとの書籍数を分析
    yearly_counts = analyze_books_by_year(book_df)

    # 出版社ごとの書籍数を分析
    publisher_counts = analyze_books_by_publisher(book_df)

    # 著者ごとの書籍数を分析
    author_counts = analyze_books_by_author(book_df)

    # コンテンツタグごとの書籍数を分析
    tag_counts = analyze_books_by_content_tag(book_df)

    # 月ごとの購入書籍数を分析
    monthly_counts = analyze_monthly_purchases(book_df)

    # 接続を閉じる
    conn.close()

    # 結果を辞書にまとめる
    results = {
        "book_df": book_df,
        "yearly_counts": yearly_counts,
        "publisher_counts": publisher_counts,
        "author_counts": author_counts,
        "tag_counts": tag_counts,
        "monthly_counts": monthly_counts,
    }

    return results
