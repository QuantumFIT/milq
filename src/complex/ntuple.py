class nTuple:
    # TODO: refactor
    def __init__(self, elements=None, name=None, n=0, generator=None, bound=None):
        
        # n has to be a power of 2
        if n != 0:
            # https://stackoverflow.com/questions/600293/how-to-check-if-a-number-is-a-power-of-2
            if not (n and (n & (n - 1)) == 0):
                raise ValueError("n has to be a power of 2")
        self.n = n
        if generator is not None:
            self.gen = generator
        else:
            self.gen = None
            
        if self.gen is None:
            self.elements = elements
            return

        if name is not None:
            safe = name.replace('[', '_').replace(']', '')
            self.elements = [generator.declare_integer(f"{safe}_{i}") for i in range(n)]
        else:
            self.elements = [generator.format_integer(e) for e in elements]
    
    def _use_pysmt(self):
        if self.gen is not None and self.gen.name == 'PortfolioSolver':
            return True
        return False
            
    def copy(self):
        return nTuple(elements=self.elements.copy(), n=self.n, generator=self.gen)

    def _coeffs(self):
        return self.elements

    def __add__(self, other):
        if self.gen is None:
            return nTuple(elements=[self.elements[i] + other.elements[i] for i in range(self.n)], n=self.n, generator=self.gen)
        elif self._use_pysmt():
            return nTuple(elements=[Plus(self._to_pysmt_expr(self.elements[i]), self._to_pysmt_expr(other.elements[i])) for i in range(self.n)], n=self.n, generator=self.gen)
        else:
            return nTuple(elements=[f"(+ {self.elements[i]} {other.elements[i]})" for i in range(self.n)], n=self.n, generator=self.gen)

    def __sub__(self, other):
        if self.gen is None:
            return nTuple(elements=[self.elements[i] - other.elements[i] for i in range(self.n)], n=self.n, generator=self.gen)
        elif self._use_pysmt():
            return nTuple(elements=[Minus(self._to_pysmt_expr(self.elements[i]), self._to_pysmt_expr(other.elements[i])) for i in range(self.n)], n=self.n, generator=self.gen)
        else:
            return nTuple(elements=[f"(- {self.elements[i]} {other.elements[i]})" for i in range(self.n)], n=self.n, generator=self.gen)

    def __mul__(self, other):
        if self.gen is None:
            elements = [0] * self.n
            for i in range(self.n):
                for j in range(other.n):
                    target_index = (i + j) % self.n
                    amplitude = self.elements[i] * other.elements[j]
                    elements[target_index] += amplitude
            return nTuple(elements=elements, n=self.n, generator=self.gen)
        elif self._use_pysmt():
            elements = [None] * self.n
            for i in range(self.n):
                elements[i] = Int(0)
            for i in range(self.n):
                for j in range(other.n):
                    target_index = (i + j) % self.n
                    e1 = self._to_pysmt_expr(self.elements[i])
                    e2 = self._to_pysmt_expr(other.elements[j])
                    amplitude = Times(e1, e2)
                    if elements[target_index] is None or (isinstance(elements[target_index], int) and elements[target_index] == 0):
                        elements[target_index] = amplitude
                    else:
                        elements[target_index] = Plus(elements[target_index], amplitude)
            return nTuple(elements=elements, n=self.n, generator=self.gen)
        else:
            elements = [0] * self.n
            for i in range(self.n):
                for j in range(other.n):
                    target_index = (i + j) % self.n
                    amplitude = f"(* {self.elements[i]} {other.elements[j]})"
                    if elements[target_index] == 0:
                        elements[target_index] = amplitude
                    else:
                        elements[target_index] = f"(+ {elements[target_index]} {amplitude})"
            return nTuple(elements=elements, n=self.n, generator=self.gen)
    
    def _to_pysmt_expr(self, value):
        if isinstance(value, str):
            if self.gen is not None and hasattr(self.gen, 'symbols') and value in self.gen.symbols:
                return self.gen.symbols[value]
            try:
                if '.' in value:
                    return Real(float(value))
                else:
                    return Int(int(value))
            except:
                return value
        return value
    
    def __eq__(self, other):
        if self._use_pysmt():
            eqs = []
            for i in range(self.n):
                e1 = self._to_pysmt_expr(self.elements[i])
                e2 = self._to_pysmt_expr(other.elements[i])
                eqs.append(Equals(e1, e2))
            return And(*eqs)
        else:
            eqs = [
                f"(= {self.elements[i]} {other.elements[i]})" for i in range(self.n)
            ]
            return f"(and {' '.join(eqs)})"

    def __repr__(self):
        return f"({', '.join(str(e) for e in self.elements)})"

    @classmethod
    def one(cls, generator, n):
        elems = [0] * n
        elems[0] = 1
        return cls(elements=elems, n=n, generator=generator)
    
    @classmethod
    def zero(cls, generator, n):
        elems = [0] * n
        return cls(elements=elems, n=n, generator=generator)
    
    @classmethod
    def inv_sqrt2(cls, generator, n):
        # should not be used
        raise ValueError("inv_sqrt2 is not used for nTuple")

    @classmethod
    def one_half(cls, generator, n):
        # should not be used
        raise ValueError("one_half is not used for nTuple")
    
    @classmethod
    def i_half(cls, generator, n):
        raise ValueError("i_half is not used for nTuple")

    @classmethod
    def omega(cls, generator, n):
        raise ValueError("omega is not used for nTuple")

    @classmethod
    def minus_one(cls, generator, n):
        elems = [0] * n
        elems[0] = -1
        return cls(elements=elems, n=n, generator=generator)

    @classmethod
    def i_phase(cls, generator, n):
        raise ValueError("i_phase is not used for nTuple")

    @classmethod
    def t_phase(cls, generator, n):
        raise ValueError("t_phase is not used for nTuple")
    
    def multiply_by_omega(self, generator):
        # HERE omega is e^(ipi/4) -- T gate phase
        shifts = int(self.n/4) 
        # swap the sign of the last shifts numbers, shift to the right by shifts
        if self.gen is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = -self.elements[self.n - shifts + i]
            for i in range(shifts, self.n):
                elems[i] = self.elements[i - shifts]
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[i] = Minus(Int(0), self._to_pysmt_expr(self.elements[self.n - shifts + i]))
            for i in range(shifts, self.n):
                elems[i] = self._to_pysmt_expr(self.elements[i - shifts])
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = f"(- 0 {self.elements[self.n - shifts + i]})"
            for i in range(shifts, self.n):
                elems[i] = f"{self.elements[i - shifts]}"
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        
    def multiply_by_omega_counter(self, generator):
        shifts = int(self.n/4) 
        if self.gen is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = -self.elements[i]
            for i in range(shifts, self.n):
                elems[i - shifts] = self.elements[i]
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = Minus(Int(0), self.elements[i])
            for i in range(shifts, self.n):
                elems[i - shifts] = self.elements[i]
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = f"(- 0 {self.elements[i]})"
            for i in range(shifts, self.n):
                elems[i - shifts] = f"{self.elements[i]}"
            return nTuple(elements=elems, n=self.n, generator=self.gen)
    
    def multiply_by_i(self, generator):
        shifts = int(self.n/2)
        if self.gen is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = -self.elements[self.n - shifts + i]
            for i in range(shifts, self.n):
                elems[i] = self.elements[i - shifts]
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[i] = Minus(Int(0), self._to_pysmt_expr(self.elements[self.n - shifts + i]))
            for i in range(shifts, self.n):
                elems[i] = self._to_pysmt_expr(self.elements[i - shifts])
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[i] = f"(- 0 {self.elements[self.n - shifts + i]})"
            for i in range(shifts, self.n):
                elems[i] = f"{self.elements[i - shifts]}"
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        
    def multiply_by_minus_i(self, generator):
        shifts = int(self.n/2)
        if self.gen is None:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = -self.elements[i]
            for i in range(shifts, self.n):
                elems[i - shifts] = self.elements[i]
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        elif self._use_pysmt():
            elems = [None] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = Minus(Int(0), self._to_pysmt_expr(self.elements[i]))
            for i in range(shifts, self.n):
                elems[i - shifts] = self._to_pysmt_expr(self.elements[i])
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        else:
            elems = [0] * self.n
            for i in range(shifts):
                elems[self.n - shifts + i] = f"(- 0 {self.elements[i]})"
            for i in range(shifts, self.n):
                elems[i - shifts] = f"{self.elements[i]}"
            return nTuple(elements=elems, n=self.n, generator=self.gen)
        
    def multiply_by_minus_one(self, generator):
        if self.gen is None:
            return nTuple(elements=[-self.elements[i] for i in range(self.n)], n=self.n, generator=self.gen)
        elif self._use_pysmt():
            return nTuple(elements=[Minus(Int(0), self._to_pysmt_expr(self.elements[i])) for i in range(self.n)], n=self.n, generator=self.gen)
        else:
            return nTuple(elements=[f"(- 0 {self.elements[i]})" for i in range(self.n)], n=self.n, generator=self.gen)
        
    def divide_by_sqrt2(self, generator):
        if self.gen is None:
            return nTuple(elements=self.elements, n=self.n, generator=self.gen)
        elif self._use_pysmt():
            # divide_by_sqrt2 is a no-op for nTuple (just returns self)
            return nTuple(elements=self.elements, n=self.n, generator=self.gen)
        else:
            return nTuple(elements=[f"{self.elements[i]}" for i in range(self.n)], n=self.n, generator=self.gen)
        
    def to_five_tuple(self):
        elems = [0] * 4
        # if size is X, take every Yth element (X -> Y)
        # 4 -> 1, 8 -> 2, 16 -> 4
        take_every = int(self.n/4)
        j = 0
        for i in range(self.n):
            if i % take_every == 0:
                # take this element
                elems[j] = self.elements[i]
                j += 1
            elif int(self.elements[i]) != 0:
                raise ValueError("cant convert nTuple to five tuple")
        return Cyclotomic8Dyadic(a=elems[0], b=elems[1], c=elems[2], d=elems[3], generator=self.gen)
    
    def abs2(self, k):
        denominator = np.sqrt(2)**k
        num_r = 0
        num_i = 0
        for i in range(self.n):
            num_r += np.cos(np.pi * i / self.n) * self.elements[i]
            num_i += np.sin(np.pi * i / self.n) * self.elements[i]
        num_r = num_r / denominator
        num_i = num_i / denominator
        return num_r ** 2 + num_i ** 2