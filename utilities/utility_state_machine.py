
from transitions import Machine

class helperStateMachine(object):

    def __init__(self, name):
        self.name = name
        self.states = []
        self.initial_state = ""
        self.machine: Machine = None
   
    def add_states(self, states):
        self.states = states

    def add_inited_state(self, initial_state):
        self.initial_state = initial_state
    
    def init(self):
        self.machine = Machine(model=self, states=self.states, initial=self.initial_state)
    
    def add_transition(self, trigger, source, dest, before=None, after=None, conditions=None):
        self.machine.add_transition(trigger=trigger, source=source, dest=dest, before=before, after=after, conditions=conditions)


if __name__ == "__main__":
    machine = helperStateMachine("test")
    machine.add_states(["first", "second", "third"])
    machine.add_inited_state("first")
    machine.init()
    machine.add_transition("ftos", "first", "second")
    machine.add_transition("stot", "second", "third")
    machine.add_transition("ttof", "third", "first")

    machine.ftos()
    
    print(machine.state)
    machine.stot()
    print(machine.state)
    machine.ttof()
    print(machine.state)

    
    print(machine.machine.states)
    print(machine.machine.get_triggers("first"))
    


