import json
import datetime
import market, news, focus

class Ctx: pass

def main():
    m = market.run(Ctx())["artifact"]
    n = news.run(Ctx())["artifact"]
    f = focus.run(Ctx())["artifact"]
    out = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "market": m,
        "news": n,
        "focus": f,
    }
    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False)
    print("data.json written")

if __name__ == "__main__":
    main()
