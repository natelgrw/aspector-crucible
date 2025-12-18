class Component:
    def __init__(self, name):
        self.name = name
        # terminal names -> ['D', 'G', 'S', 'B']
        self.terminals = []
        self.connections = {}

    def connect(self, terminal, net):
        self.connections[terminal] = net

    def get_net(self, terminal):
        return self.connections.get(terminal)

class Transistor(Component):
    def __init__(self, name, type_):
        super().__init__(name)
        self.type = type_
        self.terminals = ['D', 'G', 'S', 'B']

class Resistor(Component):
    def __init__(self, name):
        super().__init__(name)
        self.terminals = ['P', 'N']

class Capacitor(Component):
    def __init__(self, name):
        super().__init__(name)
        self.terminals = ['P', 'N']
