import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: presentation
    color: "#070d14"

    property int currentSlide: 0

    Timer {
        interval: 6500
        running: true
        repeat: true
        onTriggered: {
            currentSlide = (currentSlide + 1) % 4
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 24
        width: parent.width * 0.85

        Image {
            source: "seclegion.png"
            width: 140
            height: 140
            anchors.horizontalCenter: parent.horizontalCenter
            fillMode: Image.PreserveAspectFit
        }

        Text {
            text: "SecLegion OS"
            font.pixelSize: 28
            font.bold: true
            color: "#00f0ff"
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: "Engineered by Ammar Elkholy — SecLegion Cybersecurity Edition"
            font.pixelSize: 14
            color: "#00ff88"
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Rectangle {
            width: parent.width
            height: 2
            color: "#00f0ff"
            opacity: 0.3
        }

        Text {
            id: slideHeader
            text: currentSlide === 0 ? "⚡ Dual Desktop Power: GNOME & Hyprland" :
                  currentSlide === 1 ? "🎯 OffSec Operator HUD & Kitty GPU Terminal" :
                  currentSlide === 2 ? "🔊 Pure PipeWire Audio with Hi-Fi Bluetooth" :
                                     "🎮 Universal Multi-GPU: AMD, Intel & NVIDIA"
            font.pixelSize: 18
            font.bold: true
            color: "#00ff88"
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            id: slideBody
            text: currentSlide === 0 ? "Switch seamlessly between fluid GNOME Wayland and dynamic Hyprland with Waybar, Rofi, and SwayNC." :
                  currentSlide === 1 ? "GPU-accelerated Kitty terminal, dynamic tun0 VPN pill, target lock, and fast modern CLI tools." :
                  currentSlide === 2 ? "Low-latency PipeWire sound engine with LDAC, aptX HD, and SBC-XQ wireless audio support." :
                                     "Built-in kernel drivers for AMD Radeon, Intel Iris Xe, and NVIDIA Hybrid Prime laptops."
            font.pixelSize: 13
            color: "#93c5fd"
            wrapMode: Text.WordWrap
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
