# Skill: PyQt6 线程安全编码

## 触发条件
编写任何涉及网络请求、文件 IO、OCR、模型调用、OpenCV、time.sleep 的 PyQt6 代码时。

## 规则
1. 主线程禁止任何 >50ms 操作。看到阻塞调用立即重构为 Worker。
2. 一律使用 moveToThread 范式，固定模板：
   - Worker(QObject)：业务信号 + finished + errorOccurred + stop() + _stopped 标志
   - run() 整体 try/except，异常通过 errorOccurred.emit(str(e)) 上报
   - 连接顺序：业务槽在前，thread.quit 清理链在后，thread.finished → deleteLater
3. Worker 和 Thread 必须存为窗口/界面实例属性，禁止局部变量。
4. 子线程只发信号传纯数据(str/int/QImage)，禁止触碰任何 QWidget/QPixmap。
5. closeEvent 中必须 stopAll：worker.stop() → thread.quit() → thread.wait(3000)。

## 反例（发现即重写）
- ❌ QThread 子类里直接操作 UI
- ❌ processEvents() 解决卡顿
- ❌ worker 未持有引用（局部变量会被 GC）
- ❌ run() 中裸抛异常不捕获

## 信号量校验清单
[ ] 耗时操作在哪个线程？ [ ] worker 引用谁持有？ [ ] 退出时如何停？ [ ] 异常如何到用户？
