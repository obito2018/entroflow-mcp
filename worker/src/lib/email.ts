import { Env } from "../lib/types";

const FROM_EMAIL = "noreply@entroflow.ai";
const FROM_NAME = "EntroFlow";

export async function sendEmail(to: string, subject: string, html: string): Promise<boolean> {
  try {
    const res = await fetch("https://api.mailchannels.net/tx/v1/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: FROM_EMAIL, name: FROM_NAME },
        subject,
        content: [{ type: "text/html", value: html }],
      }),
    });
    return res.status === 202 || res.status === 200;
  } catch {
    return false;
  }
}

function emailTemplate(title: string, body: string): string {
  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="max-width:480px;margin:40px auto;background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
    <div style="background:#1d1d1f;padding:28px 32px">
      <span style="color:#fff;font-size:20px;font-weight:600;letter-spacing:-0.5px">EntroFlow</span>
    </div>
    <div style="padding:32px">
      <h2 style="margin:0 0 16px;font-size:22px;font-weight:600;color:#1d1d1f;letter-spacing:-0.3px">${title}</h2>
      ${body}
      <p style="margin:24px 0 0;font-size:12px;color:#86868b">如果你没有请求此操作，请忽略此邮件。<br>If you did not request this, please ignore this email.</p>
    </div>
  </div>
</body>
</html>`;
}

export function verifyEmailTemplate(code: string): string {
  return emailTemplate("验证你的邮箱 / Verify your email", `
    <p style="margin:0 0 20px;font-size:15px;color:#1d1d1f;line-height:1.6">
      请使用以下验证码完成邮箱验证。验证码 10 分钟内有效。<br>
      Use the code below to verify your email. Valid for 10 minutes.
    </p>
    <div style="background:#f5f5f7;border-radius:12px;padding:20px;text-align:center;margin:0 0 20px">
      <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#1d1d1f;font-family:monospace">${code}</span>
    </div>
  `);
}

export function resetPasswordTemplate(code: string): string {
  return emailTemplate("重置密码 / Reset Password", `
    <p style="margin:0 0 20px;font-size:15px;color:#1d1d1f;line-height:1.6">
      请使用以下验证码重置你的密码。验证码 10 分钟内有效。<br>
      Use the code below to reset your password. Valid for 10 minutes.
    </p>
    <div style="background:#f5f5f7;border-radius:12px;padding:20px;text-align:center;margin:0 0 20px">
      <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#1d1d1f;font-family:monospace">${code}</span>
    </div>
  `);
}

export function loginCodeTemplate(code: string): string {
  return emailTemplate("登录验证码 / Login Code", `
    <p style="margin:0 0 20px;font-size:15px;color:#1d1d1f;line-height:1.6">
      请使用以下验证码登录你的账号。验证码 10 分钟内有效。<br>
      Use the code below to log in to your account. Valid for 10 minutes.
    </p>
    <div style="background:#f5f5f7;border-radius:12px;padding:20px;text-align:center;margin:0 0 20px">
      <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#1d1d1f;font-family:monospace">${code}</span>
    </div>
  `);
}
