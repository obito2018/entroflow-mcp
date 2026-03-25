# EntroFlow 使用指南

EntroFlow 让你通过 AI Agent 控制各类智能设备，包括智能家居、机器人、机械臂及其他智能硬件。无需写代码，直接用自然语言下指令。

---

## 什么时候用

用户提到控制、查询、操作任何智能设备时，使用 EntroFlow 工具。包括但不限于：智能家居（灯、电视、空调、传感器等）、机器人、机械臂、实验室设备及其他可联网控制的硬件。

---

## 首次使用流程

第一次使用时，按以下顺序调用工具：

```
1. platform_list          → 查看可用平台，确认平台 id
2. platform_install       → 安装平台连接包
3. login_start            → 发起登录，获取二维码或表单
4. （用户操作）           → 扫码或填写表单
5. login_poll             → 轮询登录状态，直到返回 ok
6. device_discover        → 拉取用户设备列表，查看哪些支持
7. device_install         → 安装设备驱动（每个 model 只需一次）
8. device_register        → 注册设备到本地（需向用户确认信息）
9. device_control         → 控制设备
```

### login_start 返回 type=qrcode

**必须先把 `qr_url` 完整展示给用户，等用户确认看到链接后，再做任何其他操作。禁止在用户看到链接之前调用 `login_poll`。**

展示方式：

> 请在浏览器中打开以下链接，用米家 App 扫描二维码：
> [qr_url]
> 扫码完成后告诉我。

用户确认扫码后，调用 `login_poll(platform, session_id)` 检查状态。
如果返回 `waiting`，告知用户仍在等待，待用户说扫码完成后再次调用，不要自动循环轮询。
如果返回 `expired`，重新调用 `login_start` 获取新二维码。

### login_start 返回 type=form

将 `fields` 里的字段逐一展示给用户填写，收集完毕后调用 `login_poll` 提交。

### device_register 注意事项

调用前**必须向用户确认**以下三个字段，不得自行填写或使用"未知"等占位值：

- `name`：设备昵称，方便日后识别（如"客厅大电视"、"书房挂灯"）
- `location`：设备所在位置（如"客厅"、"主卧"、"办公室"）
- `remark`：备注信息，描述设备特征或用途（如"65寸Mini LED"、"书桌上方"）

`did` 和 `model` 从 `device_discover` 结果中获取，`platform` 从 `platform_list` 获取。

---

## 日常使用

设备注册后，后续直接控制，无需重新登录：

```
1. device_search    → 找到设备，查看支持的动作
2. device_control   → 执行动作
```

或查询状态：

```
1. device_search    → 找到设备
2. device_status    → 查询当前状态
```

---

## 新增设备

账号下有新设备时：

```
1. login_start + login_poll   → 重新登录（如 token 已过期）
2. device_discover            → 重新发现设备
3. device_install             → 安装新设备驱动
4. device_register            → 注册新设备
```

---

## 各平台登录说明

| 平台 | 登录方式 | 说明 |
|------|----------|------|
| mihome（米家） | 二维码扫码 | 用米家 App 扫码，有效期 300 秒 |

---

## 设备不支持怎么办

`device_discover` 返回【暂不支持】的设备，可以访问 entroflow.ai 官网提交支持需求。

---

## 注意事项

- `login_start` 发起后后台自动开始轮询，用户扫码期间无需额外操作
- 同一平台无需重复安装，`platform_install` 会自动跳过已安装的
- 同一设备驱动无需重复安装，`device_install` 会自动跳过已安装的
- 设备控制失败提示"未登录"时，重新走登录流程即可
