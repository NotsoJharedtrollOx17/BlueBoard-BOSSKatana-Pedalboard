import unittest

from blueboard_macro_handler.katana.commands import createProgramChange
from blueboard_macro_handler.katana.transport import MidoMidiTransport, resolveOutputName


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


class FakeMido:
    Message = FakeMessage

    def __init__(self, names=("KATANA",)) -> None:
        self.names = names
        self.opened = []
        self.port = FakePort()

    def get_output_names(self):
        return list(self.names)

    def open_output(self, name):
        self.opened.append(name)
        return self.port


class KatanaTransportTests(unittest.TestCase):
    def testResolutionPrefersExactThenUniqueSubstring(self) -> None:
        names = ("KATANA PRIMARY", "KATANA CTRL")
        self.assertEqual(resolveOutputName("KATANA CTRL", names), "KATANA CTRL")
        self.assertEqual(resolveOutputName("primary", names), "KATANA PRIMARY")

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

    def testTransportRejectsSendBeforeOpen(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not open"):
            MidoMidiTransport(FakeMido()).send(createProgramChange(0, 0))


if __name__ == "__main__":
    unittest.main()
