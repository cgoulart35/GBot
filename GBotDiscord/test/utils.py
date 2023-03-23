#region IMPORTS

#endregion

class AsyncIter:
    def __init__(self, items):
        self.items = items

    async def __aiter__(self):
        for item in self.items:
            yield item

class SideEffectBuilder:
    def __init__(self, keyArgument, map):
        self.keyArgument = keyArgument
        self.map = map

    def side_effect(self, *args, **kwargs):
        return self.map[args[self.keyArgument]]