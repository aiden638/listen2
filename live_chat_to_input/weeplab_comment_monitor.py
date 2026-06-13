import asyncio
from playwright.async_api import async_playwright


COMMENT_SELECTOR = ".chat_box"      # 실제 위플랩 댓글 박스 selector로 수정 필요
NAME_SELECTOR = ".name"             # 닉네임 selector로 수정 필요
TEXT_SELECTOR = ".text"             # 댓글 내용 selector로 수정 필요


def is_valid_chat(chat):
    """
    감지한 댓글이 실제 사용자 댓글인지 검사한다.
    """
    if not chat.get("text"):
        return False

    if not chat.get("name"):
        return False

    # 위플랩 시스템 메시지나 관리자 계정을 제외하고 싶을 때 사용
    blocked_names = ["구독자", "스트리머", "팬클럽", "매니저"]

    if chat["name"] in blocked_names:
        return False

    return True


async def get_chat(page):
    """
    현재 페이지에서 댓글 목록을 읽어온다.
    """
    elements = await page.query_selector_all(COMMENT_SELECTOR)
    chats = []

    for index, el in enumerate(elements):
        data_id = await el.get_attribute("data-id")
        data_name = await el.get_attribute("data-name")

        name_el = await el.query_selector(NAME_SELECTOR)
        text_el = await el.query_selector(TEXT_SELECTOR)

        name = await name_el.text_content() if name_el else data_name
        text = await text_el.text_content() if text_el else ""

        name = name.strip() if name else ""
        text = text.strip() if text else ""

        chat = {
            "id": data_id if data_id else str(index),
            "name": name,
            "text": text,
        }

        if is_valid_chat(chat):
            chat["key"] = f"{chat['id']}_{chat['name']}_{chat['text']}"
            chats.append(chat)

    return chats


class CommentMonitor:
    def __init__(self, url, on_new_chat, interval=0.5, headless=False):
        self.url = url
        self.on_new_chat = on_new_chat
        self.interval = interval
        self.headless = headless
        self.previous_chats = set()
        self._stop_event = asyncio.Event()

    async def _monitor(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless
            )

            page = await browser.new_page()
            await page.goto(self.url)

            async def on_page_close():
                print("브라우저가 닫혀 모니터링을 종료합니다.")
                self._stop_event.set()

            page.on("close", lambda _: asyncio.create_task(on_page_close()))

            try:
                print("댓글 감지를 시작합니다.")

                while not self._stop_event.is_set():
                    try:
                        chats = await get_chat(page)
                        new_chats = []

                        for chat in chats:
                            if chat["key"] not in self.previous_chats:
                                new_chats.append(chat)

                        self.previous_chats.clear()

                        for chat in chats:
                            self.previous_chats.add(chat["key"])

                        if new_chats:
                            await self.on_new_chat(new_chats)

                        await asyncio.sleep(self.interval)

                    except Exception as e:
                        if "Browser.close: Connection closed" in str(e):
                            print("브라우저 연결이 끊어졌습니다.")
                            break

                        print("댓글 감지 중 오류 발생:", e)
                        await asyncio.sleep(self.interval)

            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    async def start(self):
        await self._monitor()

    def stop(self):
        self._stop_event.set()


async def on_new_chat(chats):
    """
    새 댓글이 들어왔을 때 실행되는 함수.
    나중에 여기에 시로AI, 음악 추천 AI, 자동 응답 로직을 연결하면 된다.
    """
    for chat in chats:
        print(f"[새 댓글] {chat['name']}: {chat['text']}")


async def main():
    url = "https://weflab.com/page/hN_G2suSk2ZuYGw"

    monitor = CommentMonitor(
        url=url,
        on_new_chat=on_new_chat,
        interval=0.5,
        headless=False
    )

    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())