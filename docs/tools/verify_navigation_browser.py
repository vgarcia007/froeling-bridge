"""Shared browser checks for the responsive navigation, without data mutations."""


def click(browser, selector):
    point = browser.js("""(() => {
      const element = document.querySelector(%r);
      element.scrollIntoView({block: 'center'});
      const box = element.getBoundingClientRect();
      return {x: box.x + box.width / 2, y: box.y + box.height / 2};
    })()""" % selector)
    browser.call('Input.dispatchMouseEvent', dict(type='mousePressed', button='left', clickCount=1, **point))
    browser.call('Input.dispatchMouseEvent', dict(type='mouseReleased', button='left', clickCount=1, **point))


def verify_navigation(browser):
    for width in [320, 390, 650, 768, 1440]:
        browser.call('Emulation.setDeviceMetricsOverride', dict(width=width, height=1000,
                     deviceScaleFactor=1, mobile=width<=650))
        mobile = width <= 650
        browser.wait("getComputedStyle(document.querySelector('#sidebar-content')).display " + ("==='none'" if mobile else "!=='none'"))
        if mobile:
            click(browser, '#navigation-toggle')
            browser.wait("document.querySelector('#navigation-toggle').getAttribute('aria-expanded')==='true'")
        assert browser.js("[...document.querySelectorAll('.main-nav button')].every(x=>x.getBoundingClientRect().height>=44)")
        assert browser.js("document.querySelector('.main-nav').scrollWidth<=document.querySelector('.main-nav').clientWidth"), width
        original = browser.js("document.querySelector('#account-name').textContent")
        browser.js("document.querySelector('#account-name').textContent='a'.repeat(64)")
        assert browser.js('document.documentElement.scrollWidth<=window.innerWidth'), width
        assert browser.js("document.querySelector('#account-panel').getBoundingClientRect().top>=document.querySelector('.main-nav').getBoundingClientRect().bottom")
        browser.js("document.querySelector('#account-name').textContent="+repr(original))
        if mobile:
            # Keyboard closing returns focus, then a real Tab reaches the first item.
            browser.call('Input.dispatchKeyEvent', dict(type='keyDown', key='Escape', code='Escape'))
            browser.call('Input.dispatchKeyEvent', dict(type='keyUp', key='Escape', code='Escape'))
            assert browser.js("document.activeElement.id==='navigation-toggle'")
            click(browser, '#navigation-toggle')
            browser.call('Input.dispatchKeyEvent', dict(type='keyDown', key='Tab', code='Tab', windowsVirtualKeyCode=9))
            browser.call('Input.dispatchKeyEvent', dict(type='keyUp', key='Tab', code='Tab', windowsVirtualKeyCode=9))
            assert browser.js("document.activeElement.id==='nav-plant'")
        for view in ['menu', 'values', 'times', 'errors', 'collector', 'plant']:
            if mobile and browser.js("document.querySelector('#navigation-toggle').getAttribute('aria-expanded')==='false'"):
                click(browser, '#navigation-toggle')
            click(browser, '#nav-'+view)
            browser.wait("!document.querySelector('#"+view+"-view').hidden")
            assert browser.js("document.activeElement.id==='view-title'")
            assert browser.js("document.querySelectorAll('.main-nav [aria-current=page]').length===1")
            if mobile:
                assert browser.js("getComputedStyle(document.querySelector('#sidebar-content')).display==='none'")
            assert browser.js('document.documentElement.scrollWidth<=window.innerWidth'), (width, view)
    # Short desktop window: the bottom actions remain reachable by scrolling.
    browser.call('Emulation.setDeviceMetricsOverride', dict(width=768, height=400, deviceScaleFactor=1, mobile=False))
    browser.js("document.querySelector('#logout').scrollIntoView({block:'center'})")
    assert browser.js("(() => { const r=document.querySelector('#logout').getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight; })()")
    # Switching from desktop to mobile while focus is in the menu must not hide focus.
    browser.js("document.querySelector('#nav-plant').focus()")
    browser.call('Emulation.setDeviceMetricsOverride', dict(width=390, height=1000, deviceScaleFactor=1, mobile=True))
    browser.wait("document.activeElement.id==='navigation-toggle'")
    assert browser.js("document.querySelector('#navigation-toggle').getAttribute('aria-expanded')==='false'")
    click(browser, '#navigation-toggle')
    click(browser, '#navigation-toggle')
    assert browser.js("getComputedStyle(document.querySelector('#sidebar-content')).display==='none'")
