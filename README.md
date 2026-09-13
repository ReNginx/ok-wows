# ok-wows

[English](README_en.md) | 中文

基于 [ok-script](https://github.com/ok-oldking/ok-script) 的《战舰世界》Windows 客户端自动化。当前只做 **PVE 战斗循环**：准备舰船、加入队列、开图选点、战斗输入，打满设定场数后回港。

只识别 `WorldOfWarships64.exe`。模板按窗口比例自动选择：`21:9`、`16:10`、`16:9`。最低支持 `1280x720`。

## 功能

### Auto PVE Battle

一次性任务。启动后把游戏切到前台，用 ESC 回到港口主界面，再按下面流程跑完设定场数。

1. 选择第一艘船，打开战斗模式并选 PVE。
2. 打开加成页：如果能卸加成就全部卸掉，再 ESC 回主界面。
3. 打开装备页：如果能卸旗子就全部卸掉，再 ESC 回主界面。
4. 点击加入战斗。排队界面不操作。
5. 等待开战页出现开始按钮后点击进入战斗。
6. 确认进入战斗画面后等待 25 秒，让开局提示文字消失，再连按 10 次 `W`、按 `M` 打开大地图开始导航。每场战斗都会等待一次。
7. 在主地图范围内选航点：
   - 识别到本舰光标后，先点与它相对地图中心对称的对侧位置，等待 3 秒设置备用航点，再尝试占领区或基地，避免目标落在陆地时没有先前航路可用。
   - 识别到灰色或红色占领区时，点离本舰光标最近的一个。
   - 否则点敌方基地。
   - 占领区和敌方基地同时命中时，只保留分数更高的一类。
   - 都没有时，保留已经点击的对侧航点，不重复点击。
8. 点完航点后等路线动画稳定，用 ESC 关地图；关不掉再用 `M`。
9. 战斗中按一秒周期轮换鼠标左键（屏幕中心）、`R`、`T`、`F`，每轮输入后随机把鼠标移到画面中央，避开左侧舰船列表。地图、加载和结算时不移动；识别耗时超过一秒时本轮顺延。
10. 正常结算且场次未满时点继续战斗；最后一场点回到港口。
11. 被击沉后立刻停火，按 ESC。场次未满点继续战斗，已满则确认离开。
12. 所有战斗完成后确认回到主界面，点击 `Container-Menu`，循环点击 `Pick-Container` 和 `Confirm-Container`。点击领取后等待 10 秒仍未出现确认按钮时，视为已无更多集装箱并停止。若开启完成后关闭游戏，会在领取结束后关闭。

集装箱领取目前已提供 `21:9` 标注；其他比例需补充上述三个按钮的标注。缺少模板或确认领取页面卡住时会记录错误并停止。

可在任务配置里改：

- **Battle Count**：打几场后停止，默认 `1`，至少为 `1`。
- **Template Threshold**：模板匹配阈值，默认 `0.8`。大地图元素上限为 `0.75`，减少动态画面漏识别。

无法回到主界面、准备失败、结算超时或关键按钮找不到时会停下来，并留下日志，避免乱点。

`Ship-Icon` 只搜索左侧队伍列表，并只对模板中的黄色轮廓评分；背景不参与分数计算，当前画面的灰色舰船轮廓也会被过滤。

在任务配置中开启 **采集战斗截图（Capture Battle Dataset）** 后，从确认进入战斗满 60 秒开始，每分钟保存一张战斗界面和一张大地图，随后返回战斗界面。开关默认关闭。原始分辨率 PNG 按场次、时间戳保存在项目根目录的 `dataset/`，不改变已有航点。详见 [数据集说明](dataset/README.md)。

### Screen Recognition Test

只读检查。每 3 秒截一帧，对正式模板里的全部元素打分，并判断当前是主界面、排队、战斗、大地图、结算还是离开战斗等场景。不发送任何键鼠。用来核对标注和阈值。

## 使用

需要 Windows、Python 3.12，以及已经打开的战舰世界客户端。游戏如果以管理员权限运行，本程序也要用同样权限启动，否则截图或输入可能无效。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --index-url https://pypi.org/simple/ --upgrade pip
python -m pip install --index-url https://pypi.org/simple/ --no-deps --upgrade -r requirements.txt
python main_debug.py
```

启动后选中游戏窗口，打开 **Auto PVE Battle**，设好场数再运行。想先确认识别是否正常，先跑 **Screen Recognition Test**。

## 致谢

- [ok-script](https://github.com/ok-oldking/ok-script)
- [OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
