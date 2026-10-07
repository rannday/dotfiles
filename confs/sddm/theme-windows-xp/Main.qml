import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
  id: root
  width: 1920
  height: 1080
  color: "black"

  TextConstants { id: textConstants }

  Item {
    id: session
    property int index: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0
  }

  Connections {
    target: sddm

    onLoginSucceeded: {
      errorText.color = "steelblue"
      errorText.text = textConstants.loginSucceeded
    }

    onLoginFailed: {
      password.text = ""
      errorText.color = "red"
      errorText.text = textConstants.loginFailed
    }
  }

  Image {
    id: background
    anchors.fill: parent
    source: config.background
    fillMode: Image.PreserveAspectCrop
  }

  Rectangle {
    id: loginBox
    width: 380
    height: 250
    radius: 8
    color: "#cc111111"
    anchors.centerIn: parent

    Column {
      id: loginColumn
      width: parent.width - 48
      anchors.centerIn: parent
      spacing: 12

      TextField {
        id: username
        width: parent.width
        height: 34
        placeholderText: textConstants.promptUser
        text: userModel.lastUser
        selectByMouse: true
        focus: text.length === 0

        horizontalAlignment: TextInput.AlignHCenter
        verticalAlignment: TextInput.AlignVCenter

        background: Rectangle {
          radius: 2
          color: "#f5f5f5"
          border.color: username.activeFocus ? "#8fb2d0" : "#dddddd"
          border.width: 1
        }

        Keys.onReturnPressed: {
          sddm.login(username.text, password.text, session.index)
        }
      }

      TextField {
        id: password
        width: parent.width
        height: 34
        placeholderText: textConstants.promptPassword
        echoMode: TextInput.Password
        focus: username.text.length > 0

        horizontalAlignment: TextInput.AlignHCenter
        verticalAlignment: TextInput.AlignVCenter

        background: Rectangle {
          radius: 2
          color: "#f5f5f5"
          border.color: password.activeFocus ? "#8fb2d0" : "#dddddd"
          border.width: 1
        }

        Keys.onReturnPressed: {
          sddm.login(username.text, password.text, session.index)
        }
      }

      Row {
        id: buttonRow
        spacing: 10
        anchors.horizontalCenter: parent.horizontalCenter

        Button {
          id: rebootButton
          text: textConstants.reboot
          width: 92
          height: 38
          visible: sddm.canReboot

          background: Rectangle {
            radius: 6
            color: rebootButton.pressed ? "#3f6382" :
                   rebootButton.hovered ? "#6f98bd" :
                   "#5f86aa"
            border.color: "#8fb2d0"
            border.width: 1
          }

          contentItem: Text {
            text: rebootButton.text
            color: "#ffffff"
            font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
          }

          onClicked: sddm.reboot()
        }

        Button {
          id: powerButton
          text: textConstants.shutdown
          width: 92
          height: 38
          visible: sddm.canPowerOff

          background: Rectangle {
            radius: 6
            color: powerButton.pressed ? "#3f6382" :
                   powerButton.hovered ? "#6f98bd" :
                   "#5f86aa"
            border.color: "#8fb2d0"
            border.width: 1
          }

          contentItem: Text {
            text: powerButton.text
            color: "#ffffff"
            font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
          }

          onClicked: sddm.powerOff()
        }
      }

      Text {
        id: errorText
        width: parent.width
        text: ""
        color: "#ff7777"
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
      }
    }
  }

  Component.onCompleted: {
    if (username.text.length > 0) {
      password.forceActiveFocus()
    } else {
      username.forceActiveFocus()
    }
  }
}
