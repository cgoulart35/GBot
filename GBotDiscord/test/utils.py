#region IMPORTS

#endregion

class AsyncIter:
    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        self.index = 0
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item

class SideEffectBuilder:
    def __init__(self, keyArgument, map):
        self.keyArgument = keyArgument
        self.map = map

    def side_effect(self, *args, **kwargs):
        return self.map[args[self.keyArgument]]