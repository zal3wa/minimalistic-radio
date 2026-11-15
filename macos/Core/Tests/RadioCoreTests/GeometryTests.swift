import CoreGraphics
import Testing
@testable import RadioCore

private let screen = CGRect(x: 0, y: 0, width: 1728, height: 1080)   // below the menu bar
private let panel = CGSize(width: 412, height: 602)

@Test func panelSitsUnderTheIconAndInsideTheScreen() {
    let icon = CGRect(x: 1500, y: 1080, width: 24, height: 24)
    #expect(panelOrigin(anchor: icon, visibleFrame: screen, size: panel) == CGPoint(x: 1306, y: 470))
    let nearTheEdge = CGRect(x: 1700, y: 1080, width: 24, height: 24)
    #expect(panelOrigin(anchor: nearTheEdge, visibleFrame: screen, size: panel) == CGPoint(x: 1728 - 8 - 412, y: 470))
}

@Test func panelWithoutAnIconGoesTopRight() {
    #expect(panelOrigin(anchor: nil, visibleFrame: screen, size: panel) == CGPoint(x: 1728 - 8 - 412, y: 1080 - 8 - 602))
}
