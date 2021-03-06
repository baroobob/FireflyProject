from numpy import array, zeros
from numpy import pi, arcsin, arctan2
from numpy.linalg import norm
from bokeh.plotting import figure, show
from bokeh.models import ColumnDataSource, SingleIntervalTicker
from bokeh.io import push_notebook

# import dome projection stuff
from dome_projection import DomeProjection
from dome_projection import NoViewingDirection

NUM_PARAMETERS = 10


def read_centroid_list(filename):
    """ Read the list of centroids for the light colored spots in the
    calibration image from a file saved using domecal.exe.  """
    try:
        centroid_file = open(filename, 'r')
        centroid_list = []
        for line in centroid_file:
            try:
                row, column = line.split(", ")
                centroid_list.append([float(row), float(column)])
            except:
                # ignore other lines in the file
                pass
        #print centroid_list
    except:
        print "Error reading list of centroids from", filename
        exit()
    return centroid_list


def directions_to_angles(directions):
    x = array([direction[0] for direction in directions])
    y = array([direction[1] for direction in directions])
    z = array([direction[2] for direction in directions])
    pitch = 180/pi*arcsin(z)
    yaw = 180/pi*arctan2(x,y)
    return pitch, yaw


class ParameterSearch():
    """ Create and update a graph that shows the actual viewing directions of
    the (u,v) projector coordinates in projector_points along with the viewing
    directions calculated for these points using the default parameter values
    """
    def __init__(self, filename, projector_pixel_width,
                 projector_pixel_height):
        """ Create the graph used for manual parameter searching """
        # get the calibration directions and convert them to pitch and yaw
        self.projector_pixel_width = projector_pixel_width
        self.projector_pixel_height = projector_pixel_height
        dome = DomeProjection(projector_pixel_width = projector_pixel_width,
                              projector_pixel_height = projector_pixel_height)
        directions = dome.calibration_directions
        x = array([direction[0] for direction in directions])
        y = array([direction[1] for direction in directions])
        z = array([direction[2] for direction in directions])
        self.actual_directions = directions
        actual_pitch = 180/pi*arcsin(z)
        actual_yaw = 180/pi*arctan2(x,y)
        # get the projector centroids and convert them to (u,v) coordinates
        centroids = read_centroid_list(filename)
        # convert (row, col) to (u,v)
        self.projector_points = [[c[1] + 0.5, c[0] + 0.5] for c in centroids]
        # get the default parameter values
        self.parameters = dome.get_parameters()
        # setup the figure
        fig = figure(x_range=[-180,180], y_range=(-10, 100))
        fig.axis.ticker = SingleIntervalTicker(interval=30)
        fig.grid.ticker = SingleIntervalTicker(interval=30)
        self.source = ColumnDataSource()
        fig.circle(actual_yaw, actual_pitch)# source=self.source)
        directions = self.calc_view_directions(self.parameters)
        estimated_pitch, estimated_yaw = directions_to_angles(directions)
        fig.circle(estimated_yaw, estimated_pitch, color="orange",
                        source=self.source)
        show(fig)


    def calc_view_directions(self, parameters):
        """ Calculate the viewing directions for projector_points using the
        given parameter values. """
        parameters['projector_pixel_width'] = self.projector_pixel_width
        parameters['projector_pixel_height'] = self.projector_pixel_height
        dome = DomeProjection(**parameters)
        estimated_directions = [zeros(3)]*len(self.actual_directions)
        for i in range(len(self.projector_points)):
            try:
                projector_point = self.projector_points[i]
                direction = dome.dome_display_direction(*projector_point)
                estimated_directions[i] = direction
            except NoViewingDirection:
                # For each point that has no viewing direction, set its
                # estimated viewing direction to the opposite of the actual
                # direction.  This will produce the worst possible result for
                # these points and encourage the minimization routine to look
                # elsewhere.
                estimated_directions[i] = -1*array(self.actual_directions[i])

        return estimated_directions


    def update(self, animal_y, animal_z, dome_y, dome_z, dome_radius,
               mirror_radius, projector_y, projector_z, projector_roll,
               projector_theta, projector_vertical_offset):
        """ Calculate the viewing directions for projector_points using the new
        parameter values and update the graph. """
        # calculate viewing angles
        parameters = self.parameters
        parameters['animal_position'] = array([0, animal_y, animal_z])
        parameters['dome_center'] = array([0, dome_y, dome_z])
        parameters['dome_radius'] = dome_radius
        parameters['mirror_radius'] = mirror_radius
        parameters['projector_focal_point'] = array([0, projector_y, projector_z])
        parameters['projector_roll'] = projector_roll
        parameters['projector_theta'] = projector_theta
        parameters['projector_vertical_offset'] = projector_vertical_offset
        estimated_directions = self.calc_view_directions(parameters)
        pitch, yaw = directions_to_angles(estimated_directions)
        # update the data
        self.source.data['x'] = yaw
        self.source.data['y'] = pitch
        #self.source.push_notebook()
        push_notebook()

        """
        Calculate the length of the difference between each actual direction
        and it's corresponding estimated direction.  Return the sum of these
        differences.
        """
        sum_of_errors = 0
        for i, actual_direction in enumerate(self.actual_directions):
            #[x, y, z] = actual_direction
            #yaw = 180/pi*arctan2(x, y)
            #pitch = 180/pi*arcsin(z)
            error = norm(actual_direction - estimated_directions[i])
            sum_of_errors = sum_of_errors + error
            #[x, y, z] = estimated_directions[i]
            #est_yaw = 180/pi*arctan2(x, y)
            #est_pitch = 180/pi*arcsin(z)
        return sum_of_errors


