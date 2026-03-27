✅ パターン①：GitHubに既にリポジトリがある場合（普通はこちら）

例：
sanyo-PMS/production-platform を初めてローカルに持ってくる

🔹 手順
① 保存したい場所へ移動
cd C:\Users\mieka\Documents

（PowerShell / Git Bash どちらでもOK）

② clone する
git clone https://github.com/sanyo-PMS/production-platform.git

すると：

production-platform/
 ├─ .git
 ├─ backend_api
 ├─ frontend_admin
 └─ ...

が作られます。

③ フォルダに入る
cd production-platform
④ 確認
git branch
git remote -v

remote に origin が設定されていればOK。

# 基本手順（初回push時）
① ブランチ作成
git checkout -b feature/inspection-filter

② 変更を commit
git add .
git commit -m "inspection filter 追加"

③ 初回 push（ここが重要）
git push -u origin feature/inspection-filter

-u（= --set-upstream）が超重要。
これを付けると：
ローカル ↔ リモート が紐付く
次回から git push だけでOK

続きから行うとき
git checkout develop
git pull

git checkout feature/inspection-filter
git pull


# 作業スタート
git checkout develop
git pull
git checkout -b feature/〇〇〇

＜作業終了後＞
git checkout -b feature/xxx
git add .
git commit -m "message"
git push -u origin HEAD

✅ 追跡解除手順手順
① .gitignore に追加

まず確認：
.mypy_cache/
が書いてあるか？
なければ追加。

② 追跡解除（重要）
git rm -r --cached .mypy_cache

ポイント：
--cached → Gitの追跡だけ解除
フォルダ自体は消えない
git rm -r --cached .mypy_cache
③ commit
git commit -m "remove mypy cache from tracking"
④ push
git push


# 差分パッチ手順
① featureブランチにいること確認
git branch

今いるブランチを確認。
もし違うなら：
git checkout feature/inspection-fix
git pull

② パッチをファイル保存
例：fix.patch
プロジェクトルートに保存。

③ 適用（まずは dry run 推奨）
git apply --check fix.patch

エラーが出なければOK。

④ 本適用
git apply fix.patch

⑥ コミット
git add .
git commit -m "fix: inspection approval logic"

⑦ push
git push origin feature/inspection-fix

❗ 注意点
もし git apply でエラーが出たら：
そのブランチのコードが Codex が見た状態と違う
すでに一部変更されている
この場合は無理に適用しないでください。

🔥 状況別：戻し方
🟢 ① まだ commit していない場合（安全ゾーン）

git apply fix.patch しただけなら、
まだ コミット前 ですよね？

この場合は簡単です。

✅ 全部まとめて戻す
git restore .


これで 作業ツリーを直前の状態に戻せます。

✅ 特定ファイルだけ戻す
git restore path/to/file.py

✅ 差分を確認してから戻す（おすすめ）
git diff


確認してから：

git restore .

🟡 ② commit してしまったが push していない場合

まだリモートに送っていないなら安全です。

✅ 直前のcommitを消す（変更も消す）
git reset --hard HEAD~1


※変更も完全に消えます

✅ commitだけ消して変更は残す（安全版）
git reset --soft HEAD~1


→ commitだけ戻して、修正内容は残る

🔴 ③ すでに push してしまった場合

あなたのプロジェクトでは：

mainは聖域
rewrite禁止

なので、force pushは禁止。

この場合は：

git revert <commit-hash>
で「打ち消しcommit」を作るのが正解。

# feature削除手順
✅ 前提確認（必須）
削除前に必ず確認：
PRが main にマージ済み
main が最新状態
ローカルに未コミット変更がない

git checkout develop
git pull origin develop
git status

🧹 ① ローカルブランチ削除
安全削除（推奨）
git branch -d feature/xxx

→ マージ済みでない場合はエラーになります（安全）

強制削除（非推奨）
git branch -D feature/xxx

🌍 ② リモートブランチ削除（重要）
GitHub 上に残っている場合：
git push origin --delete feature/xxx

または GitHub の PR 画面から
"Delete branch" ボタンを押す

🧼 ③ 使い終わったブランチ一覧の整理
削除済みブランチの追跡情報を掃除：
git fetch --prune