"""Kindleの蔵書情報を分析するためのCLIツール。

このモジュールは、コマンドラインからKindleの蔵書情報を分析するための
インターフェースを提供します。
"""

import argparse
import sys
import platform
from pathlib import Path
import matplotlib.pyplot as plt
from .analyzer import analyze_kindle_library

# 日本語フォントの設定
# macOSの場合はヒラギノ、Windowsの場合はMSゴシック、それ以外の場合はIPAフォントを使用
if platform.system() == "Darwin":  # macOS
    plt.rcParams["font.family"] = "Hiragino Sans GB"
elif platform.system() == "Windows":  # Windows
    plt.rcParams["font.family"] = "MS Gothic"
else:  # Linux等
    plt.rcParams["font.family"] = "IPAGothic"


def parse_args():
    """コマンドライン引数をパースする。

    Returns:
        argparse.Namespace: パースされた引数
    """
    parser = argparse.ArgumentParser(description="Kindleの蔵書情報を分析するツール")

    parser.add_argument(
        "--db-path",
        "-d",
        type=str,
        default=None,
        help="SQLiteデータベースファイルのパス（指定しない場合はデフォルトの場所を探します）",
    )

    parser.add_argument(
        "--output-dir", "-o", type=str, default="./output", help="分析結果の出力ディレクトリ（デフォルト: ./output）"
    )

    parser.add_argument("--year", "-y", action="store_true", help="年ごとの書籍数を分析")

    parser.add_argument("--publisher", "-p", action="store_true", help="出版社ごとの書籍数を分析")

    parser.add_argument("--author", "-a", action="store_true", help="著者ごとの書籍数を分析")

    parser.add_argument("--tag", "-t", action="store_true", help="コンテンツタグごとの書籍数を分析")

    parser.add_argument("--monthly", "-m", action="store_true", help="月ごとの購入書籍数を分析")

    parser.add_argument("--all", action="store_true", help="すべての分析を実行")

    return parser.parse_args()


def find_default_db_path():
    """デフォルトのデータベースファイルのパスを探す。

    Returns:
        Path: データベースファイルのパス
    """
    # Macの場合
    mac_path = Path.home() / "Library/Containers/com.amazon.Lassen/Data/Library/Protected/BookData.sqlite"
    if mac_path.exists():
        return mac_path

    # プロジェクト内のデータディレクトリを確認
    project_path = Path(__file__).parent.parent.parent / "data" / "BookData.sqlite"
    if project_path.exists():
        return project_path

    return None


def main():
    """メイン関数。"""
    args = parse_args()

    # データベースファイルのパスを取得
    db_path = args.db_path
    if db_path is None:
        db_path = find_default_db_path()
        if db_path is None:
            print("エラー: データベースファイルが見つかりません。--db-pathオプションでパスを指定してください。")
            sys.exit(1)
    else:
        db_path = Path(db_path)

    print(f"データベースファイル: {db_path}")

    # 出力ディレクトリを作成
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # データを分析
    try:
        results = analyze_kindle_library(db_path)
    except Exception as e:
        print(f"エラー: データの分析に失敗しました。{e}")
        sys.exit(1)

    # 書籍の総数を表示
    book_df = results["book_df"]
    print(f"書籍の総数: {len(book_df)}")

    # 分析オプションが何も指定されていない場合は--allと同じ扱いにする
    if not (args.year or args.publisher or args.author or args.tag or args.monthly):
        args.all = True

    # 年ごとの書籍数を分析
    if args.year or args.all:
        yearly_counts = results["yearly_counts"]
        print("\n年ごとの書籍数:")
        print(yearly_counts)

        plt.figure(figsize=(12, 6))
        ax = plt.subplot()
        ax = yearly_counts.plot(kind="bar", x="year", y="count", ax=ax)

        # 各バーの上に数値を表示
        for i, v in enumerate(yearly_counts["count"]):
            ax.text(i, v + 0.5, str(v), ha="center")

        plt.title("年ごとの書籍購入数", fontsize=16)
        plt.xlabel("年", fontsize=12)
        plt.ylabel("書籍数", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_dir / "yearly_counts.png")
        plt.close()
        print(f"グラフを保存しました: {output_dir / 'yearly_counts.png'}")

    # 出版社ごとの書籍数を分析
    if args.publisher or args.all:
        publisher_counts = results["publisher_counts"]
        print("\n出版社ごとの書籍数:")
        print(publisher_counts)

        plt.figure(figsize=(12, 8))
        ax = plt.subplot()
        ax = publisher_counts.plot(kind="barh", x="publisher", y="count", ax=ax)

        # 各バーの右に数値を表示
        for i, v in enumerate(publisher_counts["count"]):
            ax.text(v + 0.5, i, str(v), va="center")

        plt.title("出版社ごとの書籍数", fontsize=16)
        plt.xlabel("書籍数", fontsize=12)
        plt.ylabel("出版社", fontsize=12)
        plt.tight_layout()
        plt.savefig(output_dir / "publisher_counts.png")
        plt.close()
        print(f"グラフを保存しました: {output_dir / 'publisher_counts.png'}")

    # 著者ごとの書籍数を分析
    if args.author or args.all:
        author_counts = results["author_counts"]
        print("\n著者ごとの書籍数:")
        print(author_counts)

        plt.figure(figsize=(12, 8))
        ax = plt.subplot()
        ax = author_counts.plot(kind="barh", x="author", y="count", ax=ax)

        # 各バーの右に数値を表示
        for i, v in enumerate(author_counts["count"]):
            ax.text(v + 0.5, i, str(v), va="center")

        plt.title("著者ごとの書籍数", fontsize=16)
        plt.xlabel("書籍数", fontsize=12)
        plt.ylabel("著者", fontsize=12)
        plt.tight_layout()
        plt.savefig(output_dir / "author_counts.png")
        plt.close()
        print(f"グラフを保存しました: {output_dir / 'author_counts.png'}")

    # コンテンツタグごとの書籍数を分析
    if args.tag or args.all:
        tag_counts = results["tag_counts"]
        print("\nコンテンツタグごとの書籍数:")
        print(tag_counts)

        plt.figure(figsize=(10, 6))
        ax = plt.subplot()
        ax = tag_counts.plot(kind="bar", x="content_tag", y="count", ax=ax)

        # 各バーの上に数値を表示
        for i, v in enumerate(tag_counts["count"]):
            ax.text(i, v + 0.5, str(v), ha="center")

        plt.title("コンテンツタグごとの書籍数", fontsize=16)
        plt.xlabel("コンテンツタグ", fontsize=12)
        plt.ylabel("書籍数", fontsize=12)
        plt.tight_layout()
        plt.savefig(output_dir / "tag_counts.png")
        plt.close()
        print(f"グラフを保存しました: {output_dir / 'tag_counts.png'}")

    # 月ごとの購入書籍数を分析
    if args.monthly or args.all:
        monthly_counts = results["monthly_counts"]
        print("\n月ごとの購入書籍数:")
        print(monthly_counts.head())

        plt.figure(figsize=(15, 6))
        ax = plt.subplot()
        ax = monthly_counts.plot(kind="line", x="year_month", y="count", marker="o", ax=ax)

        plt.title("月ごとの購入書籍数", fontsize=16)
        plt.xlabel("年月", fontsize=12)
        plt.ylabel("書籍数", fontsize=12)
        plt.xticks(rotation=90)
        plt.tight_layout()
        plt.savefig(output_dir / "monthly_counts.png")
        plt.close()
        print(f"グラフを保存しました: {output_dir / 'monthly_counts.png'}")

    print("\n分析が完了しました。")


if __name__ == "__main__":
    main()
