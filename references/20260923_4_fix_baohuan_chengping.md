# H3 原生对白模式（2026-09-23 新增）

## 产品形态保真（自行车事故的修复）

**真根因（重要）**：H3 会把**参考图的表情带到人物脸上**——定妆图/情绪图嘴微张 → 非说话人也跟着动嘴。光改提示词不够！

**根治机制**（已代码化）：
- `tools/gen_cast_quiet.py`：生成 {{"角色"}}_quiet.png 闭嘴版定妆图（son/mother/elder 已有）
- `lib/cast.py neutralize_refs_for_silent()`：gen_shot 自动把**非说话人**的参考图换为 quiet 版（说话人保留情绪图）；无 quiet 版时情绪图降级 neutral
- 提示词双重保障：每镜追加强声明 "whoever is NOT speaking keeps lips completely closed... never moves mouth, not even slightly"

**检查方法（教训）**：5 点抽帧不够——1.26s 处微张被 0.9/1.5 两点之间的抽帧漏过；需 **0.2-0.3s 间隔密集抽帧**或视频级播放检查。

**重跑修复流程**：改 prompts.json → 删旧 shot_XX.mp4 → gen_shot 重跑 → 重拼接+重烧字幕（删 transcripts/*.json 强制重转写）

