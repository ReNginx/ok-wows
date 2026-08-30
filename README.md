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
6. 连按 10 次 `W`，再按 `M` 打开大地图。
7. 在主地图范围内选航点：
   - 识别到灰色或红色占领区时，点离本舰光标最近的一个。
   - 否则点敌方基地。
   - 占领区和敌方基地同时命中时，只保留分数更高的一类。
   - 都没有时，点与本舰光标中心对称的另一侧。
8. 点完航点后等路线动画稳定，用 ESC 关地图；关不掉再用 `M`。
9. 战斗中每秒轮换一次：鼠标左键（屏幕中心）、`R`、`T`。
10. 正常结算且场次未满时点继续战斗；最后一场点回到港口。
11. 被击沉后立刻停火，按 ESC。场次未满点继续战斗，已满则确认离开。

可在任务配置里改：

- **Battle Count**：打几场后停止，默认 `1`，至少为 `1`。
- **Template Threshold**：模板匹配阈值，默认 `0.8`。大地图元素上限为 `0.75`，减少动态画面漏识别。

无法回到主界面、准备失败、结算超时或关键按钮找不到时会停下来，并留下日志，避免乱点。

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
