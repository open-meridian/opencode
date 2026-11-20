"""The person, in a headless browser, signing in and consenting.

`opencode mcp auth meridian` prints the authorisation address and waits for the
browser to come back to its loopback callback. This reads that address from
the command's output, opens it in Chromium, signs in as the one person
(person.json, never printed), ticks exactly the rows asked for, and allows.

Usage: python3 consent.py RUN_DIR AUTH_LOG ROW [ROW...]
  ROW is `deployment_admin`, or INSTANCE:ROLE:LEVEL as the consent page's
  level options name it, or `accounts` (tick every account group offered).

Prints the consent page's rows (their `data-reach`) to RUN_DIR/consent-rows.json
for the assertions, and never a password or a token.
"""

import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

AUTHORIZE = re.compile(r"(http://meridian\.localhost/oauth/authorize\?\S+)")


def authorization_address(log, seconds=120):
    start = time.time()
    while time.time() - start < seconds:
        with open(log, errors="replace") as said:
            found = AUTHORIZE.search(said.read())
        if found:
            return found.group(1)
        time.sleep(1)
    sys.exit("consent: opencode printed no authorisation address")


def main():
    run_dir, log, rows = sys.argv[1], sys.argv[2], sys.argv[3:]
    with open(f"{run_dir}/person.json") as kept:
        person = json.load(kept)
    address = authorization_address(log)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(address)
        page.fill('input[name="name"]', person["name"])
        page.fill('input[name="password"]', person["password"])
        with page.expect_navigation():
            page.locator('input[name="password"]').press("Enter")
        if not page.locator('form[action="/oauth/authorize"] input[name="request"]').count():
            sys.exit(f"consent: no consent page after signing in ({page.url.split('?')[0]})")

        reach = page.eval_on_selector_all("[data-reach]", "els => els.map(e => e.dataset.reach)")
        with open(f"{run_dir}/consent-rows.json", "w") as out:
            json.dump(sorted(set(reach)), out)

        page.check('input[name="covers"][value="some"]')
        for row in rows:
            if row == "deployment_admin":
                page.check('input[name="deployment_admin"]')
            elif row == "accounts":
                for box in page.locator('input[name="account_group"]').all():
                    box.check()
            else:
                select = page.locator(f'select[name="level"]:has(option[value="{row}"])')
                if not select.count():
                    sys.exit(f"consent: the page offers no row {row}")
                select.select_option(row)
        with page.expect_navigation(url=re.compile(r"^http://(127\.0\.0\.1|localhost):\d+/callback")):
            page.click('button[name="decision"][value="allow"]')
        page.wait_for_load_state()
        print(f"consent: allowed {rows}; the client's callback answered", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
