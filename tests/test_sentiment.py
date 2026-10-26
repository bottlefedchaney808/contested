from contested.sentiment import classify, text_intensity


def test_bull():
    assert classify("going LONG, to the moon") == "bull"


def test_bear():
    assert classify("I am short, this is overvalued") == "bear"


def test_mixed():
    assert classify("buy the dip or sell? long calls") == "mixed"


def test_neutral():
    assert classify("the weather is nice today") == "neutral"


def test_rip_it_vs_rip_off():
    assert classify("rip it") == "bull"
    assert classify("total rip off") == "bear"


def test_intensity_base():
    assert text_intensity("buy the dip") == 1.0


def test_intensity_emphasis_caps():
    assert text_intensity("BUY THE DIP!!!") == 2.0


def test_intensity_cap_at_3():
    assert text_intensity("I'M ALL IN, bought everything!!!") == 3.0
