class Component:
    def __init__(self, name, raw_params=""):
        self.name = name
        # terminal names -> ['D', 'G', 'S', 'B']
        self.terminals = []
        self.connections = {}
        self.raw_params = raw_params

    def connect(self, terminal, net):
        self.connections[terminal] = net

    def get_net(self, terminal):
        return self.connections.get(terminal)

class Transistor(Component):
    def __init__(self, name, type_, raw_params=""):
        super().__init__(name, raw_params)
        self.type = type_
        self.terminals = ['D', 'G', 'S', 'B']

class Resistor(Component):
    def __init__(self, name, raw_params=""):
        super().__init__(name, raw_params)
        self.terminals = ['P', 'N']

class Capacitor(Component):
    def __init__(self, name, raw_params=""):
        super().__init__(name, raw_params)
        self.terminals = ['P', 'N']
