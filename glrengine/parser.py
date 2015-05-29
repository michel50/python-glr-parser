# -*- coding: utf-8 -*-
from itertools import izip, chain
from rules import RuleSet
from lr import *


class Parser(object):
    def __init__(self, grammar, scanner_kw=[], start_sym='S'):
        self.kw_set = set(scanner_kw)
        self.kw_set.add('$')
        self.R = RuleSet(grammar, self.kw_set, start_sym)
        self.I = set((r, i) for r in xrange(self.R.rules_count)
                     for i in xrange(len(self.R[r].elements) + 1))
        self.precompute_next_items()
        self.compute_lr0()
        self.LR0 = list(sorted(self.LR0))
        self.LR0_idx = {}
        for i, s in enumerate(self.LR0):
            self.LR0_idx[s] = i
        self.initial_state = self.index(self.initial_items)
        self.compute_ACTION()

    def __str__(self):
        return '\n'.join(self.R[r].name + ' = ' + ' '.join(self.R[r].elements)
                         for r in xrange(self.R.rules_count))

    def conflicts(self):
        "Returns the list of conflicts in the ACTION table."
        return filter(lambda (i, t): len(self.ACTION[i][t]) > 1,
                      ((i, t) for i, row in enumerate(self.ACTION)
                       for t in row.iterkeys()))

    def count_conflicts(self):
        "Returns the count of conflicts in the ACTION table."
        return reduce(lambda a, b: a + (len(b) > 1 and 1 or 0),
                      (a for row in self.ACTION for a in row.itervalues()),
                      0)

    def resolve_SR_conflicts(self, favor='S'):
        for s, k in self.conflicts():
            actions = self.ACTION[s][k]
            atypes = [a[0] for a in actions]
            if 'S' in atypes and 'R' in atypes:
                self.ACTION[s][k] = [a for a in actions if a[0] == favor]

    def compute_lr0(self):
        """
            Compute the LR(0) sets.
        """
        self.LR0 = set()
        x = closure([(0, 0)], self.R)
        self.initial_items = x
        stack = [tuple(sorted(x))]
        while stack:
            x = stack.pop()
            self.LR0.add(x)
            F = follow(x, self.R)
            for t, s in F.iteritems():
                s = tuple(sorted(s))
                if s not in self.LR0:
                    stack.append(s)

    def itemstr(self, item):
        """
            Stringify an item for pretty-print.
        """
        return itemstr(item, self.R)

    def itemsetstr(self, item, label=''):
        """
            Stringify an item set for pretty-print.
        """
        return itemsetstr(item, self.R, label)

    def closure(self, s):
        """
            Compute the closure of an item set.
        """
        return tuple(sorted(closure(s, self.R)))

    def kernel(self, s):
        """
            Compute the kernel of an item set.
        """
        return kernel(s)

    def index(self, s):
        """
            Returns the index of (the closure of) item set s in the LR(0) sets list.
        """
        return self.LR0_idx[self.closure(s)]

    def compute_GOTO(self):
        """
            Compute the GOTO table.
        """
        self.GOTO = []
        for s in self.LR0:
            f = {}
            for tok, dest in follow(s, self.R).iteritems():
                f[tok] = self.LR0_idx[self.closure(dest)]
            self.GOTO.append(f)

    def init_row(self, init=None):
        """
            Initialize a row of the ACTION table.
        """
        if init is None:
            init = []
        ret = {}
        for kw in self.kw_set:
            ret[kw] = [] + init
        return ret

    def precompute_next_items(self):
        self.next_list = dict((k, set()) for k in self.R if type(k) is str or type(k) is unicode)
        for item in self.I:
            r, i = item
            rule = self.R[r]
            if i > 0 and rule.elements[i - 1] in self.next_list:
                self.next_list[rule.elements[i - 1]].add(item)

    def next_items(self, item, visited=None):
        """
            Compute the yet unvisited items following the given item.
        """
        items = set()
        if visited is None:
            visited = set()
        name = self.R[item[0]].name
        for it in self.next_list[name]:
            if it not in visited:
                r, i = it
                e = self.R[r].elements
                visited.add(it)
                if len(e) == i:
                    items.update(self.next_items(it, visited))
                else:
                    items.add(it)
        return items

    def following_tokens(self, item):
        """
            Returns all tokens following the current item.
        """
        items = self.next_items(item)
        ret = first(closure(items, self.R), self.R)
        ret.add('$')
        return ret

    def compute_ACTION(self):
        """
            Compute the ACTION/GOTO table.
        """
        self.compute_GOTO()
        self.ACTION = []
        for s, g in izip(self.LR0, self.GOTO):
            action = self.init_row()

            # свертки
            for r, i in ifilter(lambda (r, i): i == len(self.R[r].elements), s):
                if not r:
                    action['$'].append(('A',))
                else:
                    for kw in self.following_tokens((r, i)):
                        action[kw].append(('R', r))

            # переносы
            for tok, dest in g.iteritems():
                action[tok].append(('S', dest))

            # commit
            self.ACTION.append(action)

    def action_to_str(self):
        """
            Stringify the ACTION/GOTO table for pretty-print.
        """

        def ac_str(c):
            return ''.join(imap(unicode, c))

        def cell(i, kw):
            if i >= 0:
                return ','.join(map(ac_str, self.ACTION[i][kw]))
            if i < 0:
                return kw != '@' and str(kw) or ''

        def col_width(kw):
            return reduce(max, chain([(type(kw) is str or type(kw) is unicode) and len(kw) or kw],
                                     (len(cell(i, kw))
                                      for i in xrange(len(self.ACTION)))))

        col_labels = sorted(self.kw_set,
                            key=lambda x: x in self.R and '|' + x
                                          or x == '$' and '|$'
                            or x)
        col_widths = [kw != '@' and col_width(kw) or 0 for kw in col_labels]

        def row(i):
            return ' | '.join(cell(i, kw).center(cw)
                              for kw, cw in izip(col_labels, col_widths))

        header = '    | ' + row(-1) + '\n'
        return header + '\n'.join(('%3i | ' % i) + row(i)
                                  for i in xrange(len(self.ACTION)))

    def dump_sets(self):
        """
            Pretty-print all LR(0) item sets.
        """
        for i, lrset in enumerate(self.LR0):
            print self.itemsetstr(lrset, i)
            print

    def itemset(self, i):
        return self.itemsetstr(self.LR0[i], i)

    @property
    def unused_rules(self):
        check = lambda i: reduce(lambda a, b: a and i not in b, self.LR0, True)
        unused_rule_indices = set(x[0] for x in filter(check, self.I))
        return set(self.R[x].name for x in unused_rule_indices)
