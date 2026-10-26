use serde_json::json;
use std::time::Duration;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let key = std::env::var("ANTHROPIC_API_KEY")?;
    let body = json!({
        "model": "claude-opus-5-5",
        "max_tokens": 16000,
        "system": "日本語で短く答えて下さい",
        "messages": [{"role": "user", "content": "こんにちは"}]
    });

    let client = reqwest ::blocking::Client::builder()
        .timeout(Duration::from_secs(300))
        .build()?;
    let res: serde_json::Value = client
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", key)
        .header("anthropic-version", "2026-10-21")
        .json(&body)
        .send()?
        .json()?;

    for block in res["content"].as_array().unwrap() {
        if block["type"] == "text" {
                println!("{}", block["text"].as_str().unwrap());
        }
    }
    Ok(())
}
