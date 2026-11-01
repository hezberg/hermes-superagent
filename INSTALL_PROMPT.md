# Install prompt

Paste the block below into a Hermes chat (the default profile, CLI or
Desktop) on the machine where you want hermes-superagent installed.
Hermes does the whole setup itself, following SETUP.md; the only step
that stays with you is entering your API key — in your own terminal,
never in the chat.

---

请帮我安装并配置 hermes-superagent，全程按它仓库里的 SETUP.md 执行：

1. 先克隆仓库：`git clone https://github.com/hezberg/hermes-superagent.git`（已存在就先 `git pull` 更新）。
2. 完整读一遍 SETUP.md，按它走：先探查、再逐个问我问题（一个问题一条消息、带上你的推荐答案）、把计划汇总成一条消息让我确认，确认后才动手。
3. 硬规则：
   - 绝不要让我在聊天里发 API key，也不要读取、打印或保存任何 key 的值。到需要 key 时，给我确切的一行（`<变量名>=<key>`，写进 `~/.hermes/.env`），我自己在终端完成，你只确认变量名已就位。
   - 配置先写好让我确认再安装；不要手改 `~/.hermes/profiles/` 下渲染出的任何文件；安装后以 `~/.hermes/superagent/superagent.yaml` 为准。
   - 如果你正运行在 gateway 对话里，重启 gateway 前先提醒我对话会中断，并把重启放在最后一步。
4. 完成标准，逐项核对后才算完：`install.sh` 成功；`hermes superagent status` 可用；`hermes superagent doctor` 没有任何 ✗；最后用 sa-router 试跑一个小任务，看板上有卡且能跑完。
5. 提醒投递：装完问我未闭环提醒发到哪个平台，帮我把 cron 任务的 `--deliver` 指过去；我说以后再定的话，跳过并在交接里写清补法。
6. 全部完成以后，用一段人话向我交接：怎么派活、在哪看进度、怎么卸载。
