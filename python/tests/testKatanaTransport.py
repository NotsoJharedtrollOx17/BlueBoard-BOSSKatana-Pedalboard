import unittest

from blueboard_macro_handler.katana.commands import createProgramChange
from blueboard_macro_handler.katana.transport import MidoMidiTransport, resolveInputName, resolveOutputName


class FakePort:
    def __init__(self) -> None:
        self.messages = []
        self.closed = False

    def send(self, message) -> None:
        self.messages.append(message)

    def close(self) -> None:
        self.closed = True


class FakeMessage:
    @staticmethod
    def from_bytes(data):
        return tuple(data)


class FakeIncomingMessage:
    def __init__(self, messageType, data) -> None:
        self.type = messageType
        self.data = tuple(data)

    def bytes(self):
        return list(self.data)


class FakeMido:
    Message = FakeMessage

    def __init__(self, names=("KATANA",)) -> None:
        self.names = names
        self.opened = []
        self.openedInputs = []
        self.port = FakePort()
        self.inputPort = FakePort()
        self.callback = None

    def get_output_names(self):
        return list(self.names)

    def get_input_names(self):
        return list(self.names)

    def open_output(self, name):
        self.opened.append(name)
        return self.port

    def open_input(self, name, callback):
        self.openedInputs.append(name)
        self.callback = callback
        return self.inputPort


class KatanaTransportTests(unittest.TestCase):
    def testResolutionPrefersExactThenUniqueSubstring(self) -> None:
        names = ("KATANA PRIMARY", "KATANA CTRL")
        self.assertEqual(resolveOutputName("KATANA CTRL", names), "KATANA CTRL")
        self.assertEqual(resolveOutputName("primary", names), "KATANA PRIMARY")
        self.assertEqual(resolveInputName("primary", names), "KATANA PRIMARY")

    def testResolutionRejectsMissingOrAmbiguousOutput(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not found"):
            resolveOutputName("KATANA", ("Other",))
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            resolveOutputName("KATANA", ("KATANA PRIMARY", "KATANA CTRL"))

    def testTransportListsOpensSendsAndCloses(self) -> None:
        mido = FakeMido(("1- KATANA",))
        transport = MidoMidiTransport(mido)
        self.assertEqual(transport.listOutputNames(), ("1- KATANA",))
        transport.open("KATANA")
        transport.send(createProgramChange(0, 0))
        self.assertEqual(mido.opened, ["1- KATANA"])
        self.assertEqual(mido.port.messages, [(0xC0, 0)])
        transport.close()
        self.assertTrue(mido.port.closed)

    def testTransportCopiesIncomingMessagesAndClosesBothPorts(self) -> None:
        mido = FakeMido(("KATANA 1",))
        received = []
        transport = MidoMidiTransport(mido)
        transport.openInput("katana", received.append)
        transport.open("katana")
        self.assertEqual((mido.openedInputs, mido.opened), (["KATANA 1"], ["KATANA 1"]))
        mido.callback(FakeIncomingMessage("sysex", (0x41, 0x00)))
        mido.callback(FakeIncomingMessage("control_change", (0xB0, 0x10, 0x7F)))
        self.assertEqual(received[0].messageType, "sysex")
        self.assertEqual(received[0].data, (0x41, 0x00))
        self.assertEqual(received[1].data, (0xB0, 0x10, 0x7F))
        transport.open("katana")
        self.assertFalse(mido.inputPort.closed)
        transport.close()
        self.assertTrue(mido.inputPort.closed)
        self.assertTrue(mido.port.closed)

    def testTransportRejectsSendBeforeOpen(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not open"):
            MidoMidiTransport(FakeMido()).send(createProgramChange(0, 0))

    def testTransportAttemptsBothClosesWhenOutputCloseFails(self) -> None:
        mido = FakeMido()
        transport = MidoMidiTransport(mido)
        transport.openInput("KATANA", lambda _message: None)
        transport.open("KATANA")

        def failClose():
            mido.port.closed = True
            raise RuntimeError("output close failed")

        mido.port.close = failClose
        with self.assertRaisesRegex(RuntimeError, "output close failed"):
            transport.close()
        self.assertTrue(mido.inputPort.closed)
        self.assertIsNone(transport.inputPort)
        self.assertIsNone(transport.outputPort)


if __name__ == "__main__":
    unittest.main()
