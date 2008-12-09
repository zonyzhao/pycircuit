# Copyright (c) 2008 Pycircuit Development Team
# See LICENSE for details.

import numpy as npy
from circuit import SubCircuit, gnd, R, VS, IS
from analysis import Analysis, AC, Noise
from pycircuit.post.internalresult import InternalResultDict
from copy import copy

class NPort(object):
    """Class to perform calculations and conversion of n-port circuits

    Attributes
    ----------
    n -- number of ports
    K -- (numpy array) transmission parameter matrix, the size is 2*n by 2*n


    """

    def __init__(self, K):
        assert npy.size(K,0) == npy.size(K,1) and npy.size(K) % 2 == 0
        
        self.K = K

        self.n = npy.size(K,0)

    @classmethod
    def from_y(self, Y):
        """Create a NPort from Y-parameters"""
        d = Y[0,0] * Y[1,1] - Y[0,1] * Y[1,0]
        return NPort(npy.array([[-Y[1,1] / Y[1,0], -1.0 / Y[1,0]],
                              [-d / Y[1,0], -Y[0,0] / Y[1,0]]]))

    @classmethod
    def from_z(self, Z):
        """Create a NPort from Z-parameters"""
        d = Z[0,0] * Z[1,1] - Z[0,1] * Z[1,0]
        return NPort(npy.array([[-Z[0,0] / Z[1,0], -d / Z[1,0]],
                              [1.0 / Z[1,0], Z[1,1] / Z[1,0]]]))

    def __mul__(self, a):
        """Cascade of two n-ports"""
        return NPort(dot(self.K, a.k))

    def __floordiv__(self, a):
        """Parallel of two n-ports

        >>> import sympy as S
        >>> a,b,c,d = S.symbols('abcd')
        >>> A = TwoPort(npy.array([[a,b], [c,d]]))
        >>> print A // A
        array([[a, 0.5*b],
           [-2c, d]], dtype=object)

        """
        return NPort.from_y(self.Y + a.Y)

    def series(self, a):
        """Series connection with another n-port

        >>> import sympy as S
        >>> a,b,c,d = S.symbols('abcd')
        >>> A = TwoPort(npy.array([[a,b], [c,d]]))
        >>> A.series(A).K
        [[ a 2*b]
         [ c/2 d]]
        
        """
        return NPort.from_z(self.Z + a.Z)

    @property
    def Z(self):
        """Return Z-parameter matrix"""
        if self.n != 2:
            raise Exception('Cannot handle %d-port parameters yet'%self.n)
        
        A = self.K
        d = A[0,0] * A[1,1] - A[0,1] * A[1,0]

        return npy.array([[A[0,0] / A[1,0], d / A[1,0]],
                        [1.0 / A[1,0], A[1,1] / A[1,0]]])
    

    @property
    def Y(self):
        """Return Y-parameter matrix"""
        if self.n != 2:
            raise Exception('Cannot handle %d-port parameters yet'%self.n)

        A = self.K
        d = A[0,0] * A[1,1] - A[0,1]*A[1,0]

        return npy.array([[A[1,1] / A[0,1], -d / A[0,1]],
                        [-1.0 / A[0,1], A[0,0] / A[0,1]]])
    
        
    def __str__(self):
        return repr(self.K)

class TwoPort(NPort):
    n = 2

class TwoPortAnalysis(Analysis):
    """Analysis to find the 2-ports parameters of a circuit

    The transmission parameters are found as:

    A = v(inp, inn)/v(outp, outn) | io = 0
    B = v(inp, inn)/i(outp, outn) | vo = 0
    C = i(inp, inn)/v(outp, outn) | io = 0
    D = i(inp, inn)/i(outp, outn) | vo = 0

    >>> c = SubCircuit()
    >>> n1 = c.add_node('net1')
    >>> n2 = c.add_node('net2')
    >>> c['R1'] = R(n1, n2, r=9e3)
    >>> c['R2'] = R(n2, gnd, r=1e3)
    >>> res = TwoPortAnalysis(c, n1, gnd, n2, gnd).solve(freqs = npy.array([0]))
    >>> res['mu'].y[0]
    (0.1+0j)
    >>> res['gamma'].y[0]
    (0.000111111111111+0j)
    >>> res['zeta'].y[0]
    (1000+0j)
    >>> res['beta'].y[0]
    (1+0j)
    
    """
    
    ACAnalysis = AC
    NoiseAnalysis = Noise
    
    def __init__(self, circuit, inp, inn, outp, outn, noise = False, 
                 noise_outquantity = 'v'):
        self.c = circuit

        self.ports = inp, inn, outp, outn

        self.noise = noise
        self.noise_outquantity = noise_outquantity
        
    def solve(self, freqs, complexfreq = False, refnode = gnd):
        result = InternalResultDict()

        abcd = self.solve_abcd(freqs, refnode=refnode, complexfreq=complexfreq)
        result['twoport'] = TwoPort(abcd)

        result['mu'] = 1/abcd[0,0]
        result['gamma'] = 1/abcd[0,1]
        result['zeta'] = 1/abcd[1,0]
        result['beta'] = 1/abcd[1,1]

        if self.noise:
            inp, inn, outp, outn = self.ports
            
            circuit_vs = copy(self.c)
            circuit_vs['VS_TwoPort'] = VS(inp, inn, vac = 1)
            
            circuit_cs = copy(self.c)
            circuit_cs['IS_TwoPort'] = IS(inp, inn, iac = 1)
            
            if self.noise_outquantity == 'i':
                for src in circuit_vs, circuit_cs:
                    src['VL'] = VS(outp, outn, vac = 0)

            if self.noise_outquantity == 'v':
                res_v = self.NoiseAnalysis(circuit_vs, 
                                           inputsrc=circuit_vs['VS_TwoPort'],
                                           outputnodes=(outp, outn)
                                           ).solve(freqs, complexfreq=complexfreq)

                res_i = self.NoiseAnalysis(circuit_cs, 
                                           inputsrc=circuit_cs['IS_TwoPort'],
                                           outputnodes=(outp, outn)
                                           ).solve(freqs, complexfreq=complexfreq)
            else:
                res_v = self.NoiseAnalysis(circuit_vs, 
                                           inputsrc=circuit_vs['VS_TwoPort'],
                                           outputsrc=circuit_vs['VL']
                                           ).solve(freqs, complexfreq=complexfreq)

                res_i = self.NoiseAnalysis(circuit_cs, 
                                           inputsrc=circuit_cs['IS_TwoPort'],
                                           outputsrc=circuit_cs['VL']
                                           ).solve(freqs, complexfreq=complexfreq)

            result['Svn'] = res_v['Svninp']
            result['Sin'] = res_i['Sininp']
            
        self.result = result

        return result

    def solve_abcd(self, freqs, refnode = gnd, complexfreq = False):
        inp, inn, outp, outn = self.ports
                
        ## Add voltage source at input port and create
        ## copies with output open and shorted respectively
        circuit_vs_open = copy(self.c)

        circuit_vs_open['VS_TwoPort'] = VS(inp, inn, vac=1)

        circuit_vs_shorted = copy(circuit_vs_open)

        circuit_vs_shorted['VL_TwoPort'] = VS(outp, outn, vac=0)

        ## Run AC-analysis on the two circuits
        ac_open = self.ACAnalysis(circuit_vs_open)
        ac_shorted = self.ACAnalysis(circuit_vs_shorted)

        res_open = ac_open.solve(freqs, refnode = refnode, 
                                 complexfreq=complexfreq)

        res_shorted = ac_shorted.solve(freqs, refnode = refnode, 
                                     complexfreq=complexfreq)
        
        A = res_open.v(inp, inn) / res_open.v(outp, outn)
        B = res_shorted.v(inp, inn) / res_shorted.i('VL_TwoPort.plus')
        C = res_open.i('VS_TwoPort.minus') / res_open.v(outp, outn)
        D = res_shorted.i('VS_TwoPort.minus') / res_shorted.i('VL_TwoPort.plus')

        return npy.array([[A,B],[C,D]], dtype=object)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
