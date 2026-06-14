def extract_gold(lines):

    block = []
    capture = False

    for line in lines:

        # safer match (CFTC sometimes changes spacing/text slightly)
        if "GOLD" in line and "COMMODITY EXCHANGE" in line:
            capture = True

        if capture:
            block.append(line)

        # stop when next market appears
        if capture and ("SILVER" in line or "Total" in line):
            break

    return block


def parse_mm(block):

    longs = []
    shorts = []

    for line in block:

        # safer matching (ignore spacing changes)
        if "Managed Money" in line and "Gold" not in line:

            # extract ALL numbers from line (more stable than index guessing)
            nums = []

            temp = ""
            for c in line:
                if c.isdigit() or c == ",":
                    temp += c
                else:
                    if temp:
                        nums.append(int(temp.replace(",", "")))
                        temp = ""

            if temp:
                nums.append(int(temp.replace(",", "")))

            # CFTC structure: last 2 numbers = long / short
            if len(nums) >= 2:
                longs.append(nums[-2])
                shorts.append(nums[-1])

    return longs, shorts
