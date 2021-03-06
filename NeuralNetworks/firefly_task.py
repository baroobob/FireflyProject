""" Only import packages needed for training the network. Network training will
sometimes be done on a remote server so no matplotlib, etc. """
import numpy as np
from numpy.random import rand, randn
import tensorflow as tf
import pickle
import signal
from neural_network import NeuralNetwork
from keypress import Keypress


class GracefulInterruptHandler(object):
    """ This interrupt handler is used to allow the user to stop training by
    hitting control-c. """

    def __init__(self, sig=signal.SIGINT):
        self.sig = sig

    def __enter__(self):
        self.interrupted = False
        self.released = False
        self.original_handler = signal.getsignal(self.sig)
        def handler(signum, frame):
            self.release()
            self.interrupted = True
        signal.signal(self.sig, handler)
        return self

    def __exit__(self, type, value, tb):
        self.release()

    def release(self):
        if self.released:
            return False
        signal.signal(self.sig, self.original_handler)
        self.released = True
        return True


# define some constants
pi = np.pi


def atan2(y, x, last_angle):
    """ Tensorflow does not have atan2 yet. Copied this from a comment on
    tensorflow's github page. """
    angle = tf.where(tf.greater(x,0.0), tf.atan(y/x), tf.zeros_like(x))
    angle = tf.where(tf.logical_and(tf.less(x,0.0), tf.greater_equal(y,0.0)),
                      tf.atan(y/x) + pi, angle)
    angle = tf.where(tf.logical_and(tf.less(x,0.0), tf.less(y,0.0)),
                      tf.atan(y/x) - pi, angle)
    angle = tf.where(tf.logical_and(tf.equal(x,0.0), tf.greater(y,0.0)),
                      0.5*pi * tf.ones_like(x), angle)
    angle = tf.where(tf.logical_and(tf.equal(x,0.0), tf.less(y,0.0)),
                      -0.5*pi * tf.ones_like(x), angle)
    angle = tf.where(tf.logical_and(tf.equal(x,0.0), tf.equal(y,0.0)),
                      np.nan * tf.zeros_like(x), angle)
    # The value of atan2(y,x) is ambigous. Adding 2*pi to any solution produces
    # another solution. This results in a discontinuity in atan2. When x is
    # negative and y goes from a small positive number to a small negative
    # number, the output of the function goes from pi to -pi. This
    # discontinuity is bad for optimization methods like SGD, Adam, and
    # Adagrad. To eliminate this discontinuity return the value in the list
    # [angle - 2*pi, angle, angle + 2*pi] that is closest to the previous
    # angle.
    delta_angle_minus_2pi = tf.abs(angle - 2*pi - last_angle)
    delta_angle = tf.abs(angle - last_angle)
    delta_angle_plus_2pi = tf.abs(angle + 2*pi - last_angle)
    angle = tf.where(tf.less(delta_angle_minus_2pi, delta_angle),
                     angle - 2*pi, angle)
    angle = tf.where(tf.less(delta_angle_plus_2pi, delta_angle),
                     angle + 2*pi, angle)
    return angle


def frobenius_norm(tensor):
    """ I'm a gonna use this for regularization. """
    square_tensor = tf.square(tensor)
    square_tensor_sum = tf.reduce_sum(square_tensor)
    frobenius_norm = tf.sqrt(square_tensor_sum)
    return frobenius_norm


def L1_norm(tensor):
    """ I'm a gonna use this for regularization. """
    L1_norm = tf.norm(tensor, ord=1)
    return L1_norm


def tfsub(a, b):
    ax = a[:,0]
    ay = a[:,1]
    bx = b[:,0]
    by = b[:,1]
    return tf.stack([ax - bx, ay - by], 1)


def rect(z):
    """ Convert polar coordinates to rectangular coordinates. """
    if isinstance(z, tf.Tensor):
        angle = z[:,0]
        radius = z[:,1]
        coordinates = tf.stack([radius*tf.cos(angle), radius*tf.sin(angle)], 1)
    elif isinstance(z, np.ndarray):
        angle = z[0][0]
        radius = z[0][1]
        coordinates = np.array([[radius*np.cos(angle), radius*np.sin(angle)]])
    else:
        raise TypeError, "unknown type in rect()"
    return coordinates


def polar(z):
    """ Convert rectangular coordinates to polar coordinates. """
    if isinstance(z, tf.Tensor):
        x = z[:,0]
        y = z[:,1]
        radius = tf.sqrt(tf.square(x) + tf.square(y))
        #angle = atan2(y, x)
        angle = tf.atan(y/x)
        coordinates = tf.stack([radius, angle], 1)
    elif isinstance(z, np.ndarray):
        x = z[0][0]
        y = z[0][1]
        radius = np.sqrt(np.square(x) + np.square(y))
        angle = np.arctan2(y, x)
        coordinates = np.array([[radius, angle]])
    else:
        raise TypeError, "unknown type in polar()"
    return coordinates


class FireflyTask(object):
    """ A simple task that requires the subject/agent to navigate to a target
    that is initially visible and then disappears. I'm going to start with a
    target that is always visible. The agent is represented by an artificial
    neural network. The inputs to the network are the direction and distance to
    the firefly in egocentric coordinates. In this coordinate system the
    direction straight in front of the agent is zero. Angles to the left are
    positive and angles to the right are negative. The outputs of the network
    correspond to a discrete rotation and movement forward or backward of the
    agent. Soft sign activation functions are used to limit how far the agent
    can rotate or move in a single time step. """
    def __init__(self, tf_session, network=None):
        """ The tf_session argument is a tensorflow session. The network
        argument is a dictionary specifying the network dimensions and
        activation functions. """
        self.tf_session = tf_session
        if network:
            if 'dimensions' in network.keys():
                self.network_dimensions = network['dimensions']
            if 'activation functions' in network.keys():
                self.activation_functions = network['activation functions']
            if 'optimizer' in network.keys():
                self.optimizer = network['optimizer']
            if 'lr' in network.keys():
                self.lr = network['lr']
        else:
            self.network_dimensions = [3,  2]
            self.activation_functions = [tf.identity]
            self.optimizer = tf.train.AdamOptimizer(learning_rate=0.1)
        #rotation_mask = tf.placeholder(tf.float32,
                                         #shape=network_outputs.get_shape())
        self.afun_names = [f.__name__ for f in self.activation_functions]
        self.network = NeuralNetwork(self.tf_session, self.network_dimensions,
                                     self.activation_functions, uniform=False)
        # Two inputs to the network are the distance and direction to the
        # firefly.
        self.direction = self.network.inputs[:,0]
        self.distance = self.network.inputs[:,1] + 0.5
        self.tolerance = 1e-2 # how close the agent has to get
        #self.tolerance = 2e-1 # how close the agent has to get
        # The network outputs are the rotation and forward movement of the
        # agent.
        self.rotation = 1.0*pi/2*self.network.outputs[:,0]
        self.step_size = 1.0*self.network.outputs[:,1]
        #self.rotation = \
                #pi/2*tf.reduce_sum(self.rotation_mask*self.network.outputs)
        #self.step_size = \
                #tf.reduce_sum(self.step_size_mask*self.network.outputs)
        # Using network outputs to update direction and distance.
        self.theta = self.direction - self.rotation
        self.x = self.distance*tf.cos(self.theta)
        self.y = self.distance*tf.sin(self.theta)
        #self.new_direction = tf.atan(self.y/(self.x - self.step_size))
        self.new_direction = atan2(self.y, (self.x - self.step_size),
                                   self.direction)
        self.new_distance2 = (tf.square(self.y)
                              + tf.square(self.x - self.step_size))
        self.new_distance = tf.sqrt(self.new_distance2)
        #self.objective = (self.new_distance2 +
                          #1.0*L1_norm(self.network.weights[0]))
        self.objective = tf.nn.softsign(self.new_distance - self.distance) + \
                #-tf.log(0.05 + tf.exp(-tf.square(self.network.weights[0]/1e-4)))
                          #1.0*L1_norm(self.network.weights[0]))
        self.minimize = self.optimizer.minimize(self.objective)
        self.tf_session.run(tf.global_variables_initializer())
        self.training_figure = None


    def new_trial(self, distance=1.0, verbose=False):
        """ Create a new firefly in front of the agent and no farther away than
        the given distance. """
        firefly = np.array([pi/2*(2*rand(1)[0] - 1), distance*rand(1)[0]])
        if verbose:
            print "Firefly postion (direction, distance):", firefly
        return firefly


    def calc_distance(self, fireflies):
        return np.max(fireflies[:,1])


    def caught(self, fireflies):
        """ Return a True if all fireflies have been caught and False
        otherwise. """
        return self.calc_distance(fireflies) <= self.tolerance


    def feed_dict(self, fireflies, learning_rate=None):
        """ Generate the feed dictionary from dictionaries that describe the
        location of the agent and the firefly. """
        rows, cols = fireflies.shape
        network_inputs = np.zeros([rows, self.network.dimensions[0]])
        network_inputs[:,0:cols] = fireflies
        # For fast convergence during training the mean value of each input
        # should be close to zero. The distance input is always positive and
        # during training it is between 0 and 1. Subtract 0.5 so the network
        # sees inputs between -0.5 and 0.5. The 0.5 will be added back for
        # calculation of the new direction and distance.
        network_inputs[:,1] -= 0.5 
        network_inputs[:,-1] = 1 # constant input
        if hasattr(self, 'lr') and learning_rate != None:
            # For manual adjustment of learning rate, GradientDescentOptimizer
            # only.
            feed = {self.network.inputs:network_inputs, self.lr:learning_rate}
        else:
            feed = {self.network.inputs:network_inputs}
        return feed


    def eval(self, x, fireflies):
        """ Return the value of a variable or tensor. """
        return self.tf_session.run(x, feed_dict=self.feed_dict(fireflies))


    def show_weight_diffs(self, new_weights, old_weights):
        """ Print the diffences between two sets of network weights. """
        for i in range(len(self.network.weights)):
            print new_weights[i] - old_weights[i]


    def move(self, fireflies):
        """ Use the network outputs to move the agent and update the firefly's
        position in the agent's egocentric coordinates. Return rotation and
        step_size so the movement can be plotted in a reference frame where the
        firefly is stationary. """
        for i in range(len(fireflies)):
            values = self.eval([self.rotation, self.step_size,
                                self.new_direction, self.new_distance],
                               np.array([fireflies[i]]))
            rotation, step_size, direction, distance = values
            fireflies[i] = np.stack([direction, distance], 1)
        return rotation[0], step_size[0]
        

    def practice(self, batch_size=1, max_trials=1000, distance=1,
                 fireflies=None, plot_progress=False):
        """ Adjust the network weights to minimize the distance to the firefly
        after taking a step where the size and direction of the step are
        determined by the network outputs. """
        if fireflies == None:
            # generate new fireflies for training
            fireflies = []
            for trial in range(batch_size*max_trials):
                fireflies.append(self.new_trial(distance=distance))
        d = self.network.dimensions
        layers = len(self.network.dimensions) - 1
        num_weights = sum([d[i]*d[i+1] for i in range(len(d)-1)])
        weights = None
        dw_means = np.zeros([layers, max_trials - 1])
        dw_stds = np.zeros([layers, max_trials - 1])
        distances = np.zeros(max_trials)
        fireflies_caught = 0
        trial = 0
        full = False
        learning_rate = 0.1
        lr_delta = 10**round(np.log10(learning_rate))
        keypress = Keypress()
        with GracefulInterruptHandler() as h:
            while trial < max_trials and not full:
                batch = np.stack(fireflies[trial*batch_size:(trial+1)*batch_size])
                # train the network
                step = 0
                old_distance = self.calc_distance(batch)
                #while step < distance and not self.caught(batch):
                while (not self.caught(batch)
                       and (step == 0 or distance_change < 0)):
                    step = step + 1
                    self.tf_session.run(self.minimize,
                                        feed_dict=self.feed_dict(batch,
                                                                 learning_rate))
                    self.move(batch)
                    new_distance = self.calc_distance(batch)
                    distance_change = new_distance - old_distance
                    old_distance = new_distance
                # count number of fireflies caught in a row
                if self.caught(batch):
                    fireflies_caught += batch_size
                else:
                    fireflies_caught = 0
                # save distance and mean and std of weight updates for plotting
                distances[trial] = self.calc_distance(batch)
                if trial > 0:
                    old_weights = weights
                    weights = [w for w in self.eval(self.network.weights, batch)]
                    dws = [weights[i] - old_weights[i]
                           for i in range(len(weights))]
                    dw_means[:,trial-1] = np.array([dw.mean() for dw in dws])
                    dw_stds[:,trial-1] = np.array([dw.std() for dw in dws])
                else:
                    weights = [w for w in self.eval(self.network.weights, batch)]
                if (trial + 1) % 100 == 0:
                    print "Practice trial:", trial + 1, \
                            "mean distance:", distances[trial - 99:trial + 1].mean()
                    if plot_progress:
                        plot_progress(self, trial, dw_means, dw_stds,
                                      distances[:trial], batch_size)
                    # Stop when the performance is good enough.
                    if fireflies_caught >= 100:
                        full = True
                # Increment the trial number.
                trial = trial + 1
                if h.interrupted:
                    # Allow user to stop training using Control-C.
                    break
                if self.optimizer.__dict__['_name'] == 'GradientDescent':
                    # For gradient descent allow user to change learning rate
                    # interactively.
                    key = keypress()
                    if key == 'up':
                        learning_rate += lr_delta
                        print "LR =", learning_rate
                    if key == 'down':
                        learning_rate -= lr_delta
                        print "LR =", learning_rate
                    if key == 'left':
                        lr_delta *= 10
                    if key == 'right':
                        lr_delta *= 0.1
        return fireflies


    def generate_trajectories(self, n, distance=10):
        """ Generate n trajectories using the current network weights. """
        origin = np.zeros(2)
        fireflies = []
        trajectories = []
        final_distances = []
        for i in range(n):
            if (i + 1) % 1000 == 0:
                print "Trajectory:", i + 1
            firefly = np.array([self.new_trial(distance=distance)])
            print "firefly location (direction, distance):", firefly
            # Rotate frame of reference 90 degrees for plotting so straight in
            # front of the agent is up instead of to the right.
            fireflies.append(np.array(firefly))
            fireflies[-1][0][0] += pi/2
            fireflies[-1] = rect(fireflies[-1])
            #self.print_weights()
            trajectory = [origin]
            agent_direction = pi/2
            steps = 0
            old_distance = self.calc_distance(firefly)
            #while (not self.caught(firefly)
                   #and (steps == 0 or distance_change < 0)):
            while steps < 30*distance:
                steps = steps + 1
                rotation, step_size = self.move(firefly)
                new_distance = self.calc_distance(firefly)
                distance_change = new_distance - old_distance
                old_distance = new_distance
                agent_direction += rotation
                step = np.array([step_size*np.cos(agent_direction),
                                 step_size*np.sin(agent_direction)])
                trajectory.append(trajectory[-1] + step)
                #print "z:", self.eval(self.network.z[-1])
                #self.print_activations()
                #print "Rotation:", rotation
                #print "Agent direction:", agent_direction
                #print "Step size:", step_size
                #print "Step:", step
                #print "New agent location:", trajectory[-1]
            trajectories.append(np.array(trajectory))
            final_distance = self.calc_distance(firefly)
            final_distances.append(np.array(final_distance))
            if self.caught(firefly):
                print "Mmmmm, yummy!"
            else:
                print "Final distance to firefly:", final_distance
        return trajectories, fireflies, final_distances


